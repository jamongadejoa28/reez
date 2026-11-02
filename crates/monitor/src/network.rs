use serde::Deserialize;
use std::{
    collections::BTreeMap,
    io::{Read, Write},
    net::{TcpStream, ToSocketAddrs},
    sync::{Arc, Mutex, mpsc},
    thread,
    time::{Duration, Instant},
};
#[derive(Clone, Default, Deserialize)]
pub struct State {
    pub connected: bool,
    pub sequence: u64,
    #[serde(default)]
    pub coils: u32,
    #[serde(default)]
    pub command_id: u64,
    #[serde(default)]
    pub command_status: String,
    #[serde(default)]
    pub error: String,
    pub values: BTreeMap<String, f64>,
    #[serde(default)]
    pub firmware_engine: String,
}
impl State {
    pub fn value(&self, k: &str) -> f64 {
        self.values.get(k).copied().unwrap_or(0.)
    }
}
#[derive(Clone)]
pub struct Shared {
    pub state: State,
    pub received: Option<Instant>,
    pub transport: bool,
    pub busy: bool,
    pub notice: String,
}
impl Default for Shared {
    fn default() -> Self {
        Self {
            state: State::default(),
            received: None,
            transport: false,
            busy: false,
            notice: "컨트롤러 응답을 기다립니다".into(),
        }
    }
}
impl Shared {
    pub fn online(&self) -> bool {
        self.transport
            && self.state.connected
            && self
                .received
                .is_some_and(|t| t.elapsed() < Duration::from_secs(4))
    }
}
pub enum Command {
    Set(String, f64),
    Stop,
}
pub fn request(endpoint: &str, path: &str, body: Option<&str>) -> Result<(u16, String), String> {
    let authority = endpoint
        .strip_prefix("http://")
        .ok_or("only http:// local simulator endpoints are supported")?
        .trim_end_matches('/');
    if authority.contains('/') {
        return Err("endpoint must not contain a path".into());
    }
    let address = if authority.contains(':') {
        authority.to_owned()
    } else {
        format!("{authority}:80")
    };
    let addr = address
        .to_socket_addrs()
        .map_err(|e| e.to_string())?
        .next()
        .ok_or("no address")?;
    let mut stream =
        TcpStream::connect_timeout(&addr, Duration::from_secs(1)).map_err(|e| e.to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .map_err(|e| e.to_string())?;
    stream
        .set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(|e| e.to_string())?;
    let payload = body.unwrap_or("");
    let req = format!(
        "{} {path} HTTP/1.0\r\nHost: {authority}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{payload}",
        if body.is_some() { "POST" } else { "GET" },
        payload.len()
    );
    stream
        .write_all(req.as_bytes())
        .map_err(|e| e.to_string())?;
    let mut bytes = Vec::new();
    stream
        .take(65537)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())?;
    if bytes.len() > 65536 {
        return Err("HTTP response too large".into());
    }
    let text = String::from_utf8(bytes).map_err(|e| e.to_string())?;
    let (header, body) = text.split_once("\r\n\r\n").ok_or("invalid HTTP response")?;
    let status = header
        .split_whitespace()
        .nth(1)
        .ok_or("missing status")?
        .parse()
        .map_err(|_| "invalid status")?;
    Ok((status, body.into()))
}
pub fn start(
    endpoint: String,
    shared: Arc<Mutex<Shared>>,
) -> (mpsc::Sender<Command>, thread::JoinHandle<()>) {
    let (tx, rx) = mpsc::channel();
    let handle = thread::spawn(move || {
        let mut pending: Option<(u64, String, f64)> = None;
        loop {
            match rx.try_recv() {
                Ok(Command::Stop) | Err(mpsc::TryRecvError::Disconnected) => break,
                Ok(Command::Set(name, value)) => {
                    let body = serde_json::json!({"name":name,"value":value}).to_string();
                    let result = request(&endpoint, "/api/command", Some(&body));
                    let mut s = shared.lock().unwrap();
                    match result {
                        Ok((202, body)) => {
                            let id = serde_json::from_str::<serde_json::Value>(&body)
                                .ok()
                                .and_then(|v| v["command_id"].as_u64())
                                .filter(|id| *id > 0);
                            if let Some(id) = id {
                                pending = Some((id, name, value));
                                s.notice = "설정 요청 전송 · 컨트롤러 확인 중".into();
                            } else {
                                s.busy = false;
                                s.notice = "설정 응답 오류 · 재조회 후 확인하세요".into();
                            }
                        }
                        other => {
                            s.busy = false;
                            s.notice = format!(
                                "설정 요청 실패 ({}) - 재조회 후 확인하세요",
                                other.map(|x| x.0).unwrap_or(0)
                            );
                        }
                    }
                }
                Err(mpsc::TryRecvError::Empty) => {}
            }
            let response = request(&endpoint, "/api/state", None)
                .ok()
                .filter(|r| r.0 == 200)
                .and_then(|(_, body)| serde_json::from_str::<State>(&body).ok())
                .filter(|state| {
                    super::FIELDS
                        .iter()
                        .all(|f| state.values.get(f.name).is_some_and(|v| v.is_finite()))
                });
            {
                let mut s = shared.lock().unwrap();
                if let Some(state) = response {
                    if let Some((id, name, value)) = &pending {
                        if state.command_id == *id
                            && !matches!(state.command_status.as_str(), "pending" | "idle")
                        {
                            s.busy = false;
                            s.notice = if state.command_status == "confirmed"
                                && (state.value(name) - value).abs() < 0.001
                            {
                                "설정 반영 확인 완료"
                            } else {
                                "설정 반영 확인 실패 · 현재 값을 확인하세요"
                            }
                            .into();
                            pending = None;
                        } else if state.command_id != *id || !state.connected {
                            s.busy = false;
                            s.notice = "설정 반영 확인 실패 · 현재 값을 확인하세요".into();
                            pending = None;
                        }
                    } else if state.command_id == 0
                        && state.connected
                        && !s.busy
                        && (!s.transport || s.notice == "컨트롤러 응답을 기다립니다")
                    {
                        s.notice = "컨트롤러 연결 정상 · 실시간 수신 중".into();
                    }
                    s.state = state;
                    s.transport = true;
                    s.received = Some(Instant::now());
                } else {
                    s.transport = false;
                    s.state.connected = false;
                    s.state.error = "HTTP connection failed".into();
                    s.busy = false;
                    pending = None;
                }
            }
            thread::sleep(Duration::from_millis(250));
        }
    });
    (tx, handle)
}
