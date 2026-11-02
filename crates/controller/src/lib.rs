#![no_std]
//! Shared Rust firmware logic: sparse Modbus RTU polling and confirmed commands.
extern crate alloc;
use alloc::string::ToString;
use core::fmt;
use serde::ser::{Serialize, SerializeMap, Serializer};
#[derive(Debug)]
pub struct Field {
    pub name: &'static str,
    pub label: &'static str,
    pub address: i32,
    pub scale: i32,
    pub is_signed: bool,
    pub writable: bool,
    pub stopped_only: bool,
    pub minimum: i32,
    pub maximum: i32,
    pub disable: i32,
}
include!(concat!(env!("OUT_DIR"), "/fields.rs"));
pub fn field_index(name: &str) -> Option<usize> {
    FIELDS.iter().position(|f| f.name == name)
}
pub fn crc(data: &[u8]) -> u16 {
    let mut value = 0xffff;
    for byte in data {
        value ^= *byte as u16;
        for _ in 0..8 {
            value = (value >> 1) ^ if value & 1 != 0 { 0xa001 } else { 0 };
        }
    }
    value
}
pub fn request(slave: u8, fc: u8, address: u16, value: u16) -> [u8; 8] {
    let [a, b] = address.to_be_bytes();
    let [c, d] = value.to_be_bytes();
    let mut result = [slave, fc, a, b, c, d, 0, 0];
    let [lo, hi] = crc(&result[..6]).to_le_bytes();
    result[6] = lo;
    result[7] = hi;
    result
}
/// A complete RTU exchange. Return zero on timeout; never retain borrowed buffers.
pub trait Transport {
    fn exchange(&mut self, request: &[u8; 8], response: &mut [u8; 256]) -> usize;
}
impl<F: FnMut(&[u8; 8], &mut [u8; 256]) -> usize> Transport for F {
    fn exchange(&mut self, request: &[u8; 8], response: &mut [u8; 256]) -> usize {
        self(request, response)
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Status {
    Idle,
    Pending,
    Confirmed,
    Mismatch,
    Cancelled,
    RejectedRunning,
    Unconfirmed,
}
impl Status {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Idle => "idle",
            Self::Pending => "pending",
            Self::Confirmed => "confirmed",
            Self::Mismatch => "mismatch",
            Self::Cancelled => "cancelled",
            Self::RejectedRunning => "rejected_running",
            Self::Unconfirmed => "unconfirmed",
        }
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Error {
    Waiting,
    Timeout,
    CrcOrSlave,
    Exception(u8),
    Shape,
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Waiting => f.write_str("Waiting for controller"),
            Self::Timeout => f.write_str("Response timeout"),
            Self::CrcOrSlave => f.write_str("Invalid CRC or slave ID"),
            Self::Exception(code) => write!(f, "Modbus exception {code}"),
            Self::Shape => f.write_str("Invalid response shape"),
        }
    }
}
#[derive(Clone)]
pub struct Monitor {
    pub holding: [u16; 59],
    pub coils: u16,
    pub connected: bool,
    pub sequence: u64,
    pub command_id: u64,
    pub last_good_ms: u64,
    pub slave: u8,
    pub status: Status,
    pub error: Option<Error>,
    pending: Option<(usize, i32)>,
}
impl Monitor {
    pub fn new(slave: u8) -> Option<Self> {
        if !(1..=247).contains(&slave) {
            return None;
        }
        Some(Self {
            holding: [0; 59],
            coils: 0,
            connected: false,
            sequence: 0,
            command_id: 0,
            last_good_ms: 0,
            slave,
            status: Status::Idle,
            error: Some(Error::Waiting),
            pending: None,
        })
    }
    pub fn raw(&self, index: usize) -> i32 {
        let f = &FIELDS[index];
        let raw = self.holding[f.address as usize];
        if f.name == "power_on" {
            (raw & 255) as i32
        } else if f.is_signed {
            raw as i16 as i32
        } else {
            raw as i32
        }
    }
    pub fn value(&self, name: &str) -> Option<f64> {
        let i = field_index(name)?;
        Some(self.raw(i) as f64 / FIELDS[i].scale as f64)
    }
    fn transact(
        &mut self,
        fc: u8,
        address: u16,
        value: u16,
        response: &mut [u8; 256],
        io: &mut impl Transport,
    ) -> bool {
        let request = request(self.slave, fc, address, value);
        let n = io.exchange(&request, response);
        let failure = if !(5..=256).contains(&n) {
            Some(Error::Timeout)
        } else if response[0] != self.slave
            || crc(&response[..n - 2]) != u16::from_le_bytes([response[n - 2], response[n - 1]])
        {
            Some(Error::CrcOrSlave)
        } else if response[1] == fc | 128 {
            Some(Error::Exception(response[2]))
        } else if response[1] != fc
            || (fc == 6 && (n != 8 || response[..8] != request))
            || (fc != 6
                && (response[2] as u16
                    != if fc == 1 {
                        value.div_ceil(8)
                    } else {
                        value * 2
                    }
                    || n != response[2] as usize + 5))
        {
            Some(Error::Shape)
        } else {
            None
        };
        if let Some(error) = failure {
            self.error = Some(error);
            false
        } else {
            true
        }
    }
    pub fn poll(&mut self, io: &mut impl Transport, now: u64) -> bool {
        const BLOCKS: &[(u16, u16)] =
            &[(1, 3), (4, 4), (10, 12), (26, 4), (35, 2), (52, 2), (58, 1)];
        let mut holding = [0; 59];
        let mut coils = 0;
        let mut response = [0; 256];
        for block in 0..2 {
            if !self.transact(1, block * 8, 8, &mut response, io) {
                return self.failed_poll();
            }
            coils |= (response[3] as u16) << (block * 8);
        }
        for &(address, count) in BLOCKS {
            if !self.transact(3, address, count, &mut response, io) {
                return self.failed_poll();
            }
            for j in 0..count as usize {
                holding[address as usize + j] =
                    u16::from_be_bytes([response[3 + j * 2], response[4 + j * 2]]);
            }
        }
        self.holding = holding;
        self.coils = coils;
        self.connected = true;
        self.last_good_ms = now;
        self.sequence = self.sequence.saturating_add(1);
        self.error = None;
        true
    }
    fn failed_poll(&mut self) -> bool {
        self.connected = false;
        if self.pending.take().is_some() {
            self.status = Status::Cancelled;
        }
        false
    }
    /// HTTP-compatible acceptance result. An accepted write is sent once by execute().
    pub fn command(&mut self, name: &str, value: f64) -> u16 {
        let Some(i) = field_index(name) else {
            return 400;
        };
        let f = &FIELDS[i];
        if !f.writable || !value.is_finite() {
            return 400;
        }
        let scaled = value * f.scale as f64;
        if !(-32768. ..=65535.).contains(&scaled) {
            return 400;
        }
        let raw = (scaled + if scaled < 0. { -0.5 } else { 0.5 }) as i32;
        if (scaled - raw as f64).abs() > 0.00001
            || ((raw < f.minimum || raw > f.maximum) && !(f.disable != -32768 && raw == f.disable))
        {
            return 400;
        }
        if !self.connected {
            return 503;
        }
        if self.pending.is_some() || (f.stopped_only && self.holding[4] & 255 != 0) {
            return 409;
        }
        self.command_id = self.command_id.saturating_add(1);
        self.pending = Some((i, raw));
        self.status = Status::Pending;
        202
    }
    pub fn execute(&mut self, io: &mut impl Transport) {
        let Some((i, value)) = self.pending.take() else {
            return;
        };
        let f = &FIELDS[i];
        let mut response = [0; 256];
        if f.stopped_only {
            if !self.transact(3, 4, 1, &mut response, io) {
                self.uncertain();
                return;
            }
            if response[4] != 0 {
                self.status = Status::RejectedRunning;
                return;
            }
        }
        if !self.transact(6, f.address as u16, value as u16, &mut response, io)
            || !self.transact(3, f.address as u16, 1, &mut response, io)
        {
            self.uncertain();
            return;
        }
        let mut readback = u16::from_be_bytes([response[3], response[4]]);
        self.holding[f.address as usize] = readback;
        if f.address == 4 {
            readback &= 255;
        }
        self.status = if readback == value as u16 {
            Status::Confirmed
        } else {
            Status::Mismatch
        };
    }
    fn uncertain(&mut self) {
        self.connected = false;
        self.status = Status::Unconfirmed;
    }
    pub fn tick(&mut self, io: &mut impl Transport, now: u64) {
        self.execute(io);
        self.poll(io, now);
    }
    pub fn snapshot(&self, now: u64) -> Snapshot<'_> {
        Snapshot { monitor: self, now }
    }
}
pub struct Snapshot<'a> {
    monitor: &'a Monitor,
    now: u64,
}
impl Serialize for Snapshot<'_> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let m = self.monitor;
        let mut map = serializer.serialize_map(Some(12))?;
        map.serialize_entry("values", &Values(m))?;
        map.serialize_entry("connected", &m.connected)?;
        map.serialize_entry("sequence", &m.sequence)?;
        map.serialize_entry("last_good_ms", &m.last_good_ms)?;
        map.serialize_entry(
            "age_ms",
            &if m.sequence == 0 {
                -1
            } else {
                self.now.saturating_sub(m.last_good_ms).min(i64::MAX as u64) as i64
            },
        )?;
        map.serialize_entry("coils", &m.coils)?;
        map.serialize_entry("slave", &m.slave)?;
        map.serialize_entry("error", &m.error.map(|e| e.to_string()).unwrap_or_default())?;
        map.serialize_entry("command_id", &m.command_id)?;
        map.serialize_entry("command_status", m.status.as_str())?;
        map.serialize_entry("firmware_engine", "rust")?;
        map.serialize_entry("transport", "modbus-rtu")?;
        map.end()
    }
}
struct Values<'a>(&'a Monitor);
impl Serialize for Values<'_> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut map = serializer.serialize_map(Some(FIELDS.len()))?;
        for (i, f) in FIELDS.iter().enumerate() {
            map.serialize_entry(f.name, &(self.0.raw(i) as f64 / f.scale as f64))?;
        }
        map.end()
    }
}
