use reez_controller::{FIELDS, Monitor, Status, Transport, crc, request};
struct Controller {
    holding: [u16; 59],
    coils: u16,
    offline: bool,
    corrupt: bool,
    lose_ack: bool,
    writes: usize,
}
impl Default for Controller {
    fn default() -> Self {
        let mut s = Self {
            holding: [0; 59],
            coils: 0,
            offline: false,
            corrupt: false,
            lose_ack: false,
            writes: 0,
        };
        s.holding[11] = 230;
        s.holding[35] = 235;
        s
    }
}
impl Transport for Controller {
    fn exchange(&mut self, req: &[u8; 8], response: &mut [u8; 256]) -> usize {
        if self.offline {
            return 0;
        }
        assert_eq!(crc(&req[..6]), u16::from_le_bytes([req[6], req[7]]));
        let a = u16::from_be_bytes([req[2], req[3]]) as usize;
        let value = u16::from_be_bytes([req[4], req[5]]);
        let mut bytes = match req[1] {
            1 => vec![1, 1, 1, (self.coils >> a) as u8],
            3 => {
                let mut b = vec![1, 3, (value * 2) as u8];
                for raw in &self.holding[a..a + value as usize] {
                    b.extend(raw.to_be_bytes());
                }
                b
            }
            6 => {
                self.writes += 1;
                self.holding[a] = value;
                if self.lose_ack {
                    return 0;
                }
                return {
                    response[..8].copy_from_slice(req);
                    8
                };
            }
            _ => panic!("unsupported function"),
        };
        let checksum = crc(&bytes);
        bytes.extend(checksum.to_le_bytes());
        if self.corrupt {
            bytes[3] ^= 1;
        }
        response[..bytes.len()].copy_from_slice(&bytes);
        bytes.len()
    }
}
#[test]
fn published_crc_vector() {
    assert_eq!(request(1, 1, 0, 8), [1, 1, 0, 0, 0, 8, 0x3d, 0xcc]);
}
#[test]
fn snapshot_is_atomic_and_signed() {
    let mut m = Monitor::new(1).unwrap();
    let mut io = Controller::default();
    io.holding[35] = (-125i16) as u16;
    io.holding[20] = (-21i16) as u16;
    io.holding[4] = 0x1701;
    assert!(m.poll(&mut io, 10));
    assert_eq!(m.value("current_temp"), Some(-12.5));
    assert_eq!(m.value("temp_calib"), Some(-2.1));
    assert_eq!(m.value("power_on"), Some(1.));
    let old = m.holding;
    io.corrupt = true;
    io.holding[35] = 400;
    assert!(!m.poll(&mut io, 20));
    assert_eq!(m.holding, old);
    assert_eq!(m.sequence, 1);
}
#[test]
fn ambiguous_write_is_never_repeated() {
    let mut m = Monitor::new(1).unwrap();
    let mut io = Controller::default();
    m.poll(&mut io, 0);
    assert_eq!(m.command("set_temp", 26.), 202);
    io.lose_ack = true;
    m.tick(&mut io, 1);
    m.tick(&mut io, 2);
    assert_eq!(io.writes, 1);
    assert_eq!(io.holding[11], 260);
    assert_eq!(m.status, Status::Unconfirmed);
}
#[test]
fn environmental_write_rechecks_current_run_state() {
    let mut m = Monitor::new(1).unwrap();
    let mut io = Controller::default();
    m.poll(&mut io, 0);
    assert_eq!(m.command("temp_calib", 1.), 202);
    io.holding[4] = 0x1701;
    m.execute(&mut io);
    assert_eq!(m.status, Status::RejectedRunning);
    assert_eq!(io.writes, 0);
}
#[test]
fn invalid_values_and_queue_do_not_write() {
    let mut m = Monitor::new(1).unwrap();
    let mut io = Controller::default();
    m.poll(&mut io, 0);
    for (name, value) in [
        ("set_temp", 23.55),
        ("set_temp", f64::NAN),
        ("set_temp", f64::INFINITY),
        ("set_hum", 80.1),
        ("power_on", 2.),
        ("current_temp", 25.),
        ("missing", 0.),
    ] {
        assert_eq!(m.command(name, value), 400);
    }
    assert_eq!(io.writes, 0);
    assert_eq!(m.command("set_temp", 25.), 202);
    assert_eq!(m.command("set_hum", 50.), 409);
}
#[test]
fn signed_write_and_disable_sentinel_confirm() {
    let mut m = Monitor::new(1).unwrap();
    let mut io = Controller::default();
    m.poll(&mut io, 0);
    for (name, value) in [("temp_calib", -2.1), ("hi_temp_set", 24.9)] {
        assert_eq!(m.command(name, value), 202);
        m.execute(&mut io);
        assert_eq!(m.status, Status::Confirmed);
        assert_eq!(m.value(name), Some(value));
    }
}
#[test]
fn map_is_complete_for_snapshot() {
    assert_eq!(FIELDS.len(), 28);
    assert!(Monitor::new(0).is_none());
    assert!(Monitor::new(248).is_none());
}
