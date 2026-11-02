use reez_controller::{FIELDS, Transport, crc};
use serde_json::{Value, json};
use std::{
    fs::{self, File},
    io::Write,
    path::PathBuf,
    thread,
    time::Duration,
};
pub struct Mock {
    registers: [u16; 59],
    known: [bool; 59],
    coils: u16,
    slave: u8,
    control: Option<PathBuf>,
    options: Value,
    trace: Option<File>,
}
impl Mock {
    pub fn new(
        slave: u8,
        control: Option<PathBuf>,
        trace: Option<PathBuf>,
    ) -> std::io::Result<Self> {
        let mut m = Self {
            registers: [0; 59],
            known: [false; 59],
            coils: 0,
            slave,
            control,
            options: json!({}),
            trace: trace.map(File::create).transpose()?,
        };
        for f in FIELDS {
            m.known[f.address as usize] = true;
        }
        for (a, v) in [
            (4, 0),
            (10, 0),
            (11, 230),
            (12, 500),
            (13, 10),
            (14, 10),
            (15, 30),
            (16, 30),
            (17, 5),
            (18, 5),
            (19, slave as u16),
            (26, 350),
            (27, 100),
            (28, 800),
            (29, 200),
            (35, 235),
            (36, 500),
            (58, 1000),
        ] {
            m.registers[a] = v;
        }
        Ok(m)
    }
    fn configure(&mut self) {
        if let Some(path) = &self.control
            && let Ok(bytes) = fs::read(path)
            && let Ok(options) = serde_json::from_slice::<Value>(&bytes)
        {
            if !options.is_object() {
                return;
            }
            for (key, address, scale) in [
                ("temperature", 35, 10.),
                ("humidity", 36, 10.),
                ("alarm_word1", 2, 1.),
                ("alarm_word2", 3, 1.),
            ] {
                if let Some(value) = options[key].as_f64() {
                    self.registers[address] = (value * scale).round() as i64 as u16;
                }
            }
            if let Some(coils) = options["coils"].as_u64() {
                self.coils = coils as u16;
            }
            self.options = options;
        }
    }
    fn frame(mut bytes: Vec<u8>) -> Vec<u8> {
        let crc = crc(&bytes);
        bytes.extend(crc.to_le_bytes());
        bytes
    }
    fn reply(&mut self, request: &[u8; 8]) -> Vec<u8> {
        self.configure();
        if request[0] != self.slave
            || crc(&request[..6]) != u16::from_le_bytes([request[6], request[7]])
            || self.options["offline"].as_bool() == Some(true)
        {
            return vec![];
        }
        let delay = self.options["delay_ms"].as_u64().unwrap_or(0).min(1500);
        thread::sleep(Duration::from_millis(delay));
        if delay >= 1500 {
            return vec![];
        }
        let fc = request[1];
        let address = u16::from_be_bytes([request[2], request[3]]) as usize;
        let value = u16::from_be_bytes([request[4], request[5]]);
        let exception = |code| Self::frame(vec![self.slave, fc | 128, code]);
        let mut response = match fc {
            1 => {
                if !matches!(address, 0 | 8) || value != 8 {
                    return exception(2);
                }
                Self::frame(vec![self.slave, fc, 1, (self.coils >> address) as u8])
            }
            3 => {
                if !(1..=125).contains(&value)
                    || address + value as usize > 59
                    || !(address..address + value as usize).all(|a| self.known[a])
                {
                    return exception(2);
                }
                let mut data = vec![self.slave, fc, (value * 2) as u8];
                for raw in &self.registers[address..address + value as usize] {
                    data.extend(raw.to_be_bytes());
                }
                Self::frame(data)
            }
            6 => {
                let Some(f) = FIELDS
                    .iter()
                    .find(|f| f.address as usize == address && f.writable)
                else {
                    return exception(2);
                };
                let raw = if f.is_signed {
                    value as i16 as i32
                } else {
                    value as i32
                };
                if (raw < f.minimum || raw > f.maximum) && (f.disable == -32768 || raw != f.disable)
                {
                    return exception(3);
                }
                self.registers[address] = value;
                if address == 4 {
                    self.coils = u16::from(value != 0);
                }
                if self.options["lost_write_ack"].as_bool() == Some(true) {
                    return vec![];
                }
                request.to_vec()
            }
            _ => return exception(1),
        };
        if self.options["bad_crc"].as_bool() == Some(true)
            && let Some(last) = response.last_mut()
        {
            *last ^= 255;
        }
        response
    }
}
impl Transport for Mock {
    fn exchange(&mut self, request: &[u8; 8], response: &mut [u8; 256]) -> usize {
        let reply = self.reply(request);
        if let Some(file) = &mut self.trace {
            let _ = writeln!(
                file,
                "{}",
                json!({"engine":"rust","request":request,"response":reply,"fc":request[1],"address":u16::from_be_bytes([request[2],request[3]])})
            );
            let _ = file.flush();
        }
        response[..reply.len()].copy_from_slice(&reply);
        reply.len()
    }
}
