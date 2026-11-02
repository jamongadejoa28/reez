//! PC execution of the same no_std Rust controller core intended for firmware.
mod mock;
use reez_controller::Monitor;
use serde_json::{Value, json};
use std::{
    io::{self, BufRead, Read, Write},
    net::{TcpListener, TcpStream},
    path::PathBuf,
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant},
};
fn stdio() -> Result<(), Box<dyn std::error::Error>> {
    let stdin = io::stdin();
    let mut lines = stdin.lock().lines();
    let mut monitor = Monitor::new(1).unwrap();
    while let Some(line) = lines.next() {
        let input: Value = serde_json::from_str(&line?)?;
        let now = input["now_ms"].as_u64().unwrap_or(0);
        let reply = match input["op"].as_str() {
            Some("init") => {
                monitor = Monitor::new(input["slave"].as_u64().unwrap_or(1) as u8)
                    .ok_or("invalid slave ID")?;
                json!({"ok":true})
            }
            Some("tick") => {
                let mut transport = |request: &[u8; 8], response: &mut [u8; 256]| -> usize {
                    println!("{}", json!({"op":"exchange","request":request}));
                    let _ = io::stdout().flush();
                    let Some(Ok(line)) = lines.next() else {
                        return 0;
                    };
                    let Ok(value) = serde_json::from_str::<Value>(&line) else {
                        return 0;
                    };
                    let Some(data) = value["response"].as_array() else {
                        return 0;
                    };
                    if data.len() > response.len() {
                        return 0;
                    }
                    for (i, byte) in data.iter().enumerate() {
                        let Some(byte) = byte.as_u64().filter(|n| *n <= 255) else {
                            return 0;
                        };
                        response[i] = byte as u8;
                    }
                    data.len()
                };
                monitor.tick(&mut transport, now);
                json!({"ok":true})
            }
            Some("state") => serde_json::to_value(monitor.snapshot(now))?,
            Some("command") => {
                let value = input["value"]
                    .as_f64()
                    .or_else(|| input["value"].as_str().and_then(|s| s.parse::<f64>().ok()))
                    .unwrap_or(f64::NAN);
                json!({"status":monitor.command(input["name"].as_str().unwrap_or(""),value)})
            }
            _ => return Err("invalid stdio operation".into()),
        };
        println!("{reply}");
        io::stdout().flush()?;
    }
    Ok(())
}
fn respond(stream: &mut TcpStream, status: u16, body: Value) -> io::Result<()> {
    let bytes = serde_json::to_vec(&body)?;
    let reason = match status {
        200 => "OK",
        202 => "Accepted",
        400 => "Bad Request",
        404 => "Not Found",
        409 => "Conflict",
        503 => "Service Unavailable",
        _ => "Internal Server Error",
    };
    write!(
        stream,
        "HTTP/1.0 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n",
        bytes.len()
    )?;
    stream.write_all(&bytes)
}
fn handle(mut stream: TcpStream, monitor: &Mutex<Monitor>, epoch: Instant) -> io::Result<()> {
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
    let mut bytes = Vec::new();
    let header_end = loop {
        let mut byte = [0];
        if stream.read(&mut byte)? == 0 {
            return Ok(());
        }
        bytes.push(byte[0]);
        if bytes.ends_with(b"\r\n\r\n") {
            break bytes.len();
        }
        if bytes.len() > 8192 {
            return respond(&mut stream, 400, json!({"error":"header too large"}));
        }
    };
    let Ok(header) = std::str::from_utf8(&bytes[..header_end]) else {
        return respond(&mut stream, 400, json!({}));
    };
    let mut lines = header.split("\r\n");
    let first = lines.next().unwrap_or("");
    let mut parts = first.split_whitespace();
    let method = parts.next().unwrap_or("");
    let path = parts.next().unwrap_or("");
    if method == "GET" && path == "/api/state" {
        let state = monitor.lock().unwrap();
        return respond(
            &mut stream,
            200,
            serde_json::to_value(state.snapshot(epoch.elapsed().as_millis() as u64))?,
        );
    }
    if method != "POST" || path != "/api/command" {
        return respond(&mut stream, 404, json!({}));
    }
    let mut length = None;
    for line in lines {
        if let Some((key, value)) = line.split_once(':') {
            if key.eq_ignore_ascii_case("transfer-encoding") {
                return respond(&mut stream, 400, json!({}));
            }
            if key.eq_ignore_ascii_case("content-length") {
                if length.is_some() {
                    return respond(&mut stream, 400, json!({}));
                }
                length = value.trim().parse::<usize>().ok();
            }
        }
    }
    let Some(length) = length.filter(|n| (1..192).contains(n)) else {
        return respond(&mut stream, 400, json!({"error":"invalid command length"}));
    };
    let mut body = vec![0; length];
    if stream.read_exact(&mut body).is_err() {
        return respond(&mut stream, 400, json!({"error":"incomplete body"}));
    }
    let Ok(input) = serde_json::from_slice::<Value>(&body) else {
        return respond(&mut stream, 400, json!({}));
    };
    let (Some(name), Some(value)) = (input["name"].as_str(), input["value"].as_f64()) else {
        return respond(&mut stream, 400, json!({}));
    };
    let mut state = monitor.lock().unwrap();
    let status = state.command(name, value);
    respond(
        &mut stream,
        status,
        json!({"status":status,"command_id":state.command_id}),
    )
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut port = 8080;
    let mut control = None;
    let mut trace = None;
    let mut slave = 1;
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--stdio-rtu" => return stdio(),
            "--port" => port = args.next().ok_or("port")?.parse::<u16>()?,
            "--slave" => slave = args.next().ok_or("slave")?.parse::<u8>()?,
            "--control-file" => control = Some(PathBuf::from(args.next().ok_or("control file")?)),
            "--trace" => trace = Some(PathBuf::from(args.next().ok_or("trace")?)),
            _ => return Err(format!("unknown argument {a}").into()),
        }
    }
    let state = Monitor::new(slave).ok_or("slave must be 1..247")?;
    let mut transport = mock::Mock::new(slave, control, trace)?;
    let monitor = Arc::new(Mutex::new(state));
    let epoch = Instant::now();
    let polling = monitor.clone();
    let listener = TcpListener::bind(("127.0.0.1", port))?;
    println!(
        "Rust firmware PC harness: http://{} (Modbus RTU core; no MCU simulation)",
        listener.local_addr()?
    );
    io::stdout().flush()?;
    thread::spawn(move || {
        loop {
            polling
                .lock()
                .unwrap()
                .tick(&mut transport, epoch.elapsed().as_millis() as u64);
            thread::sleep(Duration::from_millis(500));
        }
    });
    for stream in listener.incoming() {
        let stream = stream?;
        let state = monitor.clone();
        thread::spawn(move || {
            let _ = handle(stream, &state, epoch);
        });
    }
    Ok(())
}
