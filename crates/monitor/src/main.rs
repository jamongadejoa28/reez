#![allow(unsafe_op_in_unsafe_fn)]
mod network;
include!(concat!(env!("OUT_DIR"), "/generated.rs"));
use network::{Command, Shared};
use reez_lvgl::{color, pad, pct, sys::*, text};
use std::{
    cell::RefCell,
    collections::VecDeque,
    ptr::null_mut,
    rc::Rc,
    sync::{Arc, Mutex, mpsc},
    time::{Duration, Instant},
};
#[derive(Debug)]
pub struct Field {
    name: &'static str,
    label: &'static str,
    address: i32,
    scale: i32,
    writable: bool,
    stopped_only: bool,
    minimum: i32,
    maximum: i32,
    disable: i32,
}
include!(concat!(env!("OUT_DIR"), "/fields.rs"));
fn index(name: &str) -> usize {
    FIELDS.iter().position(|f| f.name == name).expect("field")
}
#[derive(Clone, Copy)]
enum Event {
    Navigate(usize),
    Power(i32),
    Choose(usize),
    Adjust(i32),
    Apply,
}
struct Handler {
    queue: Rc<RefCell<VecDeque<Event>>>,
    event: Event,
}
unsafe extern "C" fn callback(e: *mut lv_event_t) {
    // Callback only enqueues a Copy value. No user code runs across the C ABI.
    let h = &*(lv_event_get_user_data(e) as *const Handler);
    if let Ok(mut queue) = h.queue.try_borrow_mut() {
        queue.push_back(h.event);
    }
}
struct App {
    ui: ui::Ui,
    // Each callback user_data must stay at a fixed address when this vector grows.
    #[allow(clippy::vec_box)]
    handlers: Vec<Box<Handler>>,
    queue: Rc<RefCell<VecDeque<Event>>>,
    chart: *mut lv_obj_t,
    temp: *mut lv_chart_series_t,
    hum: *mut lv_chart_series_t,
    status: *mut lv_obj_t,
    alarms: *mut lv_obj_t,
    selected: usize,
    edit: i32,
    editing: bool,
    history: VecDeque<String>,
    previous: u32,
    last_sample: Option<Instant>,
    shared: Arc<Mutex<Shared>>,
    tx: mpsc::Sender<Command>,
}
impl App {
    unsafe fn bind(&mut self, obj: *mut lv_obj_t, event: Event) {
        let mut h = Box::new(Handler {
            queue: self.queue.clone(),
            event,
        });
        lv_obj_add_event_cb(
            obj,
            Some(callback),
            LV_EVENT_CLICKED,
            (&mut *h as *mut Handler).cast(),
        );
        self.handlers.push(h);
    }
    fn obj(&self, name: &str) -> *mut lv_obj_t {
        self.ui.object(name).expect(name)
    }
    unsafe fn label(&self, parent: *mut lv_obj_t) -> *mut lv_obj_t {
        let l = lv_label_create(parent);
        lv_obj_set_width(l, pct(100));
        lv_obj_set_style_text_font(l, self.ui.font(0).unwrap(), 0);
        text(l, "");
        l
    }
    unsafe fn new(shared: Arc<Mutex<Shared>>, tx: mpsc::Sender<Command>) -> Self {
        let mut a = Self {
            ui: ui::Ui::create(),
            handlers: vec![],
            queue: Rc::default(),
            chart: null_mut(),
            temp: null_mut(),
            hum: null_mut(),
            status: null_mut(),
            alarms: null_mut(),
            selected: index("set_temp"),
            edit: 0,
            editing: false,
            history: VecDeque::new(),
            previous: 0,
            last_sample: None,
            shared,
            tx,
        };
        for page in ["main", "settings", "trend", "status", "alarms"] {
            for (i, target) in ["main", "settings", "trend", "status", "alarms"]
                .iter()
                .enumerate()
            {
                a.bind(
                    a.obj(&format!("{page}_nav_{target}")),
                    Event::Navigate(i + 1),
                );
            }
        }
        for (name, event) in [
            ("run", Event::Power(1)),
            ("stop", Event::Power(0)),
            ("decrease", Event::Adjust(-1)),
            ("increase", Event::Adjust(1)),
            ("apply", Event::Apply),
        ] {
            a.bind(a.obj(name), event);
        }
        let list = a.obj("settings_list");
        lv_obj_add_flag(list, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_set_flex_flow(list, LV_FLEX_FLOW_COLUMN);
        pad(list, 8);
        for (i, f) in FIELDS
            .iter()
            .enumerate()
            .filter(|(_, f)| f.writable && f.address != 4)
        {
            let b = lv_button_create(list);
            lv_obj_set_size(b, pct(100), 40);
            lv_obj_set_style_bg_color(b, color(0x26394d), 0);
            let l = a.label(b);
            text(l, f.label);
            lv_obj_align(l, LV_ALIGN_CENTER, 0, 0);
            a.bind(b, Event::Choose(i));
        }
        let host = a.obj("trend_host");
        a.chart = lv_chart_create(host);
        lv_obj_set_size(a.chart, 684, 218);
        lv_obj_set_pos(a.chart, 52, 12);
        lv_obj_set_style_bg_color(a.chart, color(0x182433), 0);
        lv_chart_set_type(a.chart, LV_CHART_TYPE_LINE);
        lv_chart_set_axis_range(a.chart, LV_CHART_AXIS_PRIMARY_Y, -300, 1000);
        lv_chart_set_point_count(a.chart, 360);
        lv_obj_set_style_width(a.chart, 0, LV_PART_INDICATOR);
        lv_obj_set_style_height(a.chart, 0, LV_PART_INDICATOR);
        a.temp = lv_chart_add_series(a.chart, color(0x4fd3cb), LV_CHART_AXIS_PRIMARY_Y);
        a.hum = lv_chart_add_series(a.chart, color(0xf4b860), LV_CHART_AXIS_PRIMARY_Y);
        lv_chart_set_all_values(a.chart, a.temp, i32::MAX);
        lv_chart_set_all_values(a.chart, a.hum, i32::MAX);
        for (label, y) in [("100", 8), ("50", 92), ("0", 176), ("-30", 216)] {
            let l = a.label(host);
            lv_obj_set_pos(l, 6, y);
            lv_obj_set_width(l, 45);
            text(l, label);
        }
        for (label, x) in [("-60 min", 52), ("-30 min", 370), ("now", 692)] {
            let l = a.label(host);
            lv_obj_set_pos(l, x, 245);
            lv_obj_set_width(l, 90);
            text(l, label);
        }
        a.status = a.label(a.obj("status_host"));
        pad(a.obj("status_host"), 16);
        lv_obj_add_flag(a.obj("alarms_host"), LV_OBJ_FLAG_SCROLLABLE);
        pad(a.obj("alarms_host"), 16);
        a.alarms = a.label(a.obj("alarms_host"));
        a
    }
    fn send(&self, field: usize, value: f64) {
        let mut s = self.shared.lock().unwrap();
        let f = &FIELDS[field];
        if s.online() && !s.busy && !(f.stopped_only && s.state.value("power_on") != 0.) {
            s.busy = true;
            s.notice = "설정 요청 대기".into();
            if self.tx.send(Command::Set(f.name.into(), value)).is_err() {
                s.busy = false;
            }
        }
    }
    unsafe fn events(&mut self) {
        loop {
            let event = self.queue.borrow_mut().pop_front();
            let Some(e) = event else { break };
            match e {
                Event::Navigate(id) => self.ui.load_screen(id),
                Event::Power(value) => self.send(index("power_on"), value as f64),
                Event::Choose(i) => {
                    self.selected = i;
                    self.editing = false;
                    self.edit = (self.shared.lock().unwrap().state.value(FIELDS[i].name)
                        * FIELDS[i].scale as f64)
                        .round() as i32;
                }
                Event::Adjust(direction) => {
                    let f = &FIELDS[self.selected];
                    let step = if f.address == 58 { 100 } else { 1 };
                    if self.edit == f.disable && direction > 0 {
                        self.edit = f.minimum;
                    } else {
                        self.edit += direction * step;
                        if self.edit < f.minimum {
                            self.edit = if f.disable != -32768 {
                                f.disable
                            } else {
                                f.minimum
                            };
                        }
                        self.edit = self.edit.min(f.maximum);
                    }
                    self.editing = true;
                }
                Event::Apply => {
                    self.send(
                        self.selected,
                        self.edit as f64 / FIELDS[self.selected].scale as f64,
                    );
                    self.editing = false;
                }
            }
        }
    }
    unsafe fn refresh(&mut self) {
        let sh = self.shared.lock().unwrap().clone();
        let s = &sh.state;
        let online = sh.online();
        let clock = clock();
        let header = format!(
            "{clock}  ·  {}",
            if online {
                "통신 정상"
            } else {
                "통신 끊김"
            }
        );
        for page in ["main", "settings", "trend", "status", "alarms"] {
            let obj = self.obj(&format!("{page}_connection"));
            text(obj, &header);
            lv_obj_set_style_text_color(obj, color(if online { 0x4fd3cb } else { 0xf4b860 }), 0);
            text(
                self.obj(&format!("{page}_message")),
                if online {
                    &sh.notice
                } else if s.sequence != 0 {
                    "통신 이상 · 마지막 수신값 표시 · 조작 잠김"
                } else {
                    "컨트롤러 응답 대기 · Wokwi와 중계 연결을 확인하세요"
                },
            );
        }
        let temp = s.value("current_temp");
        let hum = s.value("current_hum");
        if s.sequence != 0 {
            for (name, value) in [
                ("current_temp", format!("{temp:.1}")),
                ("current_hum", format!("{hum:.1}")),
                ("set_temp", format!("설정  {:.1} °C", s.value("set_temp"))),
                ("set_hum", format!("설정  {:.1} %", s.value("set_hum"))),
            ] {
                text(self.obj(name), &value);
            }
        }
        let running = s.value("power_on") != 0.;
        text(
            self.obj("run_text"),
            if running {
                "운전 중"
            } else {
                "운전 시작"
            },
        );
        for (i, name) in ["run", "stop", "apply", "increase", "decrease"]
            .iter()
            .enumerate()
        {
            let disable =
                !online || sh.busy || (i >= 2 && FIELDS[self.selected].stopped_only && running);
            if disable {
                lv_obj_add_state(self.obj(name), LV_STATE_DISABLED);
            } else {
                lv_obj_remove_state(self.obj(name), LV_STATE_DISABLED);
            }
        }
        let alarms = alarm_bits(s.value("alarm_word1") as u32, s.value("alarm_word2") as u32);
        for (i, bit) in [0, 11, 12, 13, 14, 0].iter().enumerate() {
            let on = if i == 5 {
                alarms != 0
            } else {
                s.coils & (1 << bit) != 0
            };
            lv_obj_set_style_bg_color(
                self.obj(&format!("indicator_{i}")),
                color(if on {
                    if i == 5 { 0x984553 } else { 0x146c79 }
                } else {
                    0x182433
                }),
                0,
            );
        }
        let f = &FIELDS[self.selected];
        if !self.editing {
            self.edit = (s.value(f.name) * f.scale as f64).round() as i32;
        }
        text(self.obj("selected_label"), f.label);
        text(
            self.obj("selected_value"),
            &format!(
                "{:.*}",
                if f.scale == 10 { 1 } else { 0 },
                self.edit as f64 / f.scale as f64
            ),
        );
        text(
            self.obj("selected_range"),
            &format!(
                "{:.1} ~ {:.1}{}{}",
                f.minimum as f64 / f.scale as f64,
                f.maximum as f64 / f.scale as f64,
                if f.disable != -32768 {
                    " / 하한 아래: 금지"
                } else {
                    ""
                },
                if f.stopped_only {
                    "\n정지 중 변경 가능"
                } else {
                    ""
                }
            ),
        );
        if self
            .last_sample
            .is_none_or(|t| t.elapsed() >= Duration::from_secs(10))
        {
            let count = self
                .last_sample
                .map(|t| (t.elapsed().as_secs() / 10).min(360))
                .unwrap_or(1);
            for _ in 1..count {
                lv_chart_set_next_value(self.chart, self.temp, i32::MAX);
                lv_chart_set_next_value(self.chart, self.hum, i32::MAX);
            }
            lv_chart_set_next_value(
                self.chart,
                self.temp,
                if online {
                    (temp * 10.).round() as i32
                } else {
                    i32::MAX
                },
            );
            lv_chart_set_next_value(
                self.chart,
                self.hum,
                if online {
                    (hum * 10.).round() as i32
                } else {
                    i32::MAX
                },
            );
            self.last_sample = Some(Instant::now());
        }
        text(
            self.status,
            &format!(
                "운전 상태  {}       현재 전류  {:.1} A\n\n온도  {temp:.1} °C       습도  {hum:.1} %\n\n입력 포트  0x{:04X}       출력 상태  0x{:04X}\n\n냉방 단계  0x{:04X}   난방 단계  0x{:04X}   가습 단계  0x{:04X}\n\n경보 워드  0x{:04X} / 0x{:04X}",
                if running { "운전" } else { "정지" },
                s.value("current_amp"),
                s.value("input_port") as u32,
                s.coils,
                s.value("cool_ratio") as u32,
                s.value("heat_ratio") as u32,
                s.value("humid_ratio") as u32,
                s.value("alarm_word1") as u32,
                s.value("alarm_word2") as u32
            ),
        );
        if online && alarms != self.previous {
            let names = [
                "송풍기",
                "냉방1",
                "냉방2",
                "난방기",
                "가습기",
                "화재",
                "누수",
                "실린더 오염",
                "급수",
                "배수",
                "냉방3",
                "센서",
                "고온",
                "저온",
                "고습",
                "저습",
            ];
            for (i, name) in names.iter().enumerate() {
                if (alarms ^ self.previous) & (1 << i) != 0 {
                    self.history.push_front(format!(
                        "{clock}  {}  {name}",
                        if alarms & (1 << i) != 0 {
                            "발생"
                        } else {
                            "해제"
                        }
                    ));
                    self.history.truncate(50);
                }
            }
            self.previous = alarms;
            text(
                self.alarms,
                &self
                    .history
                    .iter()
                    .map(|s| format!("{s}\n"))
                    .collect::<String>(),
            );
        }
        text(
            self.obj("alarm_summary"),
            &format!(
                "{} · 현재 {}건 · 이력 {}건",
                if online {
                    "경보 상태"
                } else {
                    "마지막 수신 경보"
                },
                alarms.count_ones(),
                self.history.len()
            ),
        );
    }
    unsafe fn click(&mut self, name: &str) {
        lv_obj_send_event(self.obj(name), LV_EVENT_CLICKED, null_mut());
        self.events();
    }
}
fn alarm_bits(a: u32, b: u32) -> u32 {
    (a & 1023) | if b & (1 << 2) != 0 { 1 << 10 } else { 0 } | ((b >> 11) << 11)
}
fn clock() -> String {
    if let Ok(c) = std::env::var("REEZ_CLOCK") {
        return c;
    }
    unsafe {
        let t = libc::time(null_mut());
        let mut tm = std::mem::zeroed();
        libc::localtime_r(&t, &mut tm);
        format!("{:02}:{:02}:{:02}", tm.tm_hour, tm.tm_min, tm.tm_sec)
    }
}
unsafe fn screenshot(path: &str) -> std::io::Result<()> {
    use std::io::Write;
    let buf = lv_snapshot_take(lv_screen_active(), LV_COLOR_FORMAT_ARGB8888);
    if buf.is_null() {
        return Err(std::io::Error::other("snapshot failed"));
    }
    let width = (*buf).header.w() as usize;
    let height = (*buf).header.h() as usize;
    let stride = (*buf).header.stride() as usize;
    let size = (54 + width * height * 4) as u32;
    let mut bytes = Vec::with_capacity(size as usize);
    bytes.extend(b"BM");
    bytes.extend(size.to_le_bytes());
    bytes.extend([0u8; 4]);
    bytes.extend(54u32.to_le_bytes());
    bytes.extend(40u32.to_le_bytes());
    bytes.extend((width as i32).to_le_bytes());
    bytes.extend((-(height as i32)).to_le_bytes());
    bytes.extend(1u16.to_le_bytes());
    bytes.extend(32u16.to_le_bytes());
    bytes.extend([0u8; 24]);
    for y in 0..height {
        bytes.extend(std::slice::from_raw_parts(
            (*buf).data.add(y * stride),
            width * 4,
        ));
    }
    lv_draw_buf_destroy(buf);
    std::fs::File::create(path)?.write_all(&bytes)
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut endpoint = "http://127.0.0.1:8080".to_owned();
    let mut shot = None;
    let mut frames = 0;
    let mut page = 1;
    let mut exercise = false;
    let mut static_ui = false;
    let mut report = None;
    let mut script: Vec<serde_json::Value> = Vec::new();
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--url" => endpoint = args.next().ok_or("URL")?,
            "--frames" => frames = args.next().ok_or("frames")?.parse::<u32>()?,
            "--page" => page = args.next().ok_or("page")?.parse::<usize>()?,
            "--screenshot" => shot = Some(args.next().ok_or("screenshot")?),
            "--exercise-mock" => exercise = true,
            "--static-ui" => static_ui = true,
            "--report" => report = Some(args.next().ok_or("report")?),
            "--script" => {
                script = serde_json::from_slice(&std::fs::read(args.next().ok_or("script")?)?)?
            }
            _ => return Err(format!("unknown option {a}").into()),
        }
    }
    if !(1..=5).contains(&page) {
        return Err("--page must be 1..5".into());
    }
    unsafe {
        lv_init();
        let display = lv_sdl_window_create(800, 480);
        if display.is_null() {
            return Err("SDL display creation failed".into());
        }
        lv_sdl_window_set_title(display, c"MEX | Rust EEZ Monitor".as_ptr());
        let mouse = lv_sdl_mouse_create();
        lv_indev_set_display(mouse, display);
        lv_sdl_mousewheel_create();
        lv_sdl_keyboard_create();
        let shared = Arc::new(Mutex::new(Shared::default()));
        let (tx, thread) = network::start(endpoint, shared.clone());
        let mut app = if static_ui {
            None
        } else {
            Some(App::new(shared.clone(), tx.clone()))
        };
        let bare = if static_ui {
            Some(ui::Ui::create())
        } else {
            None
        };
        if let Some(a) = &app {
            a.ui.load_screen(page);
        } else {
            bare.as_ref().unwrap().load_screen(page);
        }
        let mut n = 0;
        let mut stage = 0;
        let mut expected = 0.;
        let mut last = Instant::now() - Duration::from_secs(1);
        loop {
            lv_timer_handler();
            if let Some(a) = &mut app {
                for step in script
                    .iter()
                    .filter(|s| s["frame"].as_u64() == Some(n as u64))
                {
                    if let Some(name) = step["select"].as_str() {
                        let field = FIELDS
                            .iter()
                            .position(|f| f.name == name)
                            .ok_or("unknown script field")?;
                        a.queue.borrow_mut().push_back(Event::Choose(field));
                    }
                    if let Some(name) = step["click"].as_str() {
                        let obj = a.ui.object(name).ok_or("unknown script widget")?;
                        if !lv_obj_has_state(obj, LV_STATE_DISABLED) {
                            lv_obj_send_event(obj, LV_EVENT_CLICKED, null_mut());
                        }
                    }
                }
                a.events();
                if last.elapsed() >= Duration::from_millis(100) {
                    a.refresh();
                    last = Instant::now();
                }
                if exercise {
                    let sh = shared.lock().unwrap().clone();
                    if sh.online() && !sh.busy && n > 50 {
                        match stage {
                            0 => {
                                expected = sh.state.value("set_temp") + 0.1;
                                a.click("main_nav_settings");
                                a.click("increase");
                                a.click("apply");
                                stage = 1;
                            }
                            1 if (sh.state.value("set_temp") - expected).abs() < 0.001 => {
                                a.click("settings_nav_main");
                                a.click("run");
                                stage = 2;
                            }
                            2 if sh.state.value("power_on") == 1. => {
                                a.click("stop");
                                stage = 3;
                            }
                            3 if sh.state.value("power_on") == 0. => {
                                a.click("main_nav_alarms");
                                stage = 4;
                                break;
                            }
                            _ => {}
                        }
                    }
                }
            }
            n += 1;
            if frames != 0 && n >= frames {
                break;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        // Finish the final screen transition before capturing/releasing screens.
        for _ in 0..25 {
            lv_timer_handler();
            std::thread::sleep(Duration::from_millis(10));
        }
        if let Some(a) = &mut app {
            a.refresh();
            if let Some(path) = report {
                let sh = shared.lock().unwrap();
                let disabled: serde_json::Map<String, serde_json::Value> =
                    ["run", "stop", "apply", "increase", "decrease"]
                        .into_iter()
                        .map(|name| {
                            (
                                name.into(),
                                lv_obj_has_state(a.obj(name), LV_STATE_DISABLED).into(),
                            )
                        })
                        .collect();
                let active = ["main", "settings", "trend", "status", "alarms"]
                    .into_iter()
                    .find(|name| a.obj(name) == lv_screen_active());
                let result = serde_json::json!({"online":sh.online(),"pending":sh.busy,"notice":sh.notice,"history_count":a.history.len(),"history":a.history,"alarms":a.previous,"controls_disabled":disabled,"screen":active,"selected":FIELDS[a.selected].name,"edit_raw":a.edit,"values":sh.state.values,"command_id":sh.state.command_id});
                std::fs::write(path, serde_json::to_vec_pretty(&result)?)?;
            }
        }
        if let Some(path) = shot {
            screenshot(&path)?;
        }
        tx.send(Command::Stop)?;
        thread.join().map_err(|_| "network thread failed")?;
        drop(app);
        drop(bare);
        lv_deinit();
        if exercise && stage != 4 {
            return Err(format!("UI exercise incomplete at stage {stage}").into());
        }
    }
    Ok(())
}
