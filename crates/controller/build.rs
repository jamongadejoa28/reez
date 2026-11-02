use std::{env, fs, path::PathBuf};
fn main() {
    println!("cargo:rerun-if-changed=data/registers.json");
    let rows: Vec<serde_json::Value> =
        serde_json::from_slice(&fs::read("data/registers.json").unwrap()).unwrap();
    let mut text = String::from("pub static FIELDS: &[Field] = &[\n");
    for s in rows {
        let scale = s["scale"].as_i64().unwrap();
        let addr = s["addr"].as_i64().unwrap();
        let raw = |key: &str| (s[key].as_f64().unwrap_or(0.) * scale as f64).round() as i32;
        text += &format!(
            "Field{{name:{:?},label:{:?},address:{},scale:{scale},is_signed:{},writable:{},stopped_only:{},minimum:{},maximum:{},disable:{}}},\n",
            s["code"].as_str().unwrap(),
            s["nameKo"].as_str().unwrap(),
            addr - 1,
            s["signed"].as_bool().unwrap(),
            s["writable"].as_bool().unwrap(),
            matches!(addr, 21 | 22 | 27 | 28 | 29 | 30 | 53 | 54 | 59),
            raw("min"),
            raw("max"),
            if s["disableValue"].is_number() {
                raw("disableValue")
            } else {
                -32768
            }
        );
    }
    text += "];";
    fs::write(
        PathBuf::from(env::var("OUT_DIR").unwrap()).join("fields.rs"),
        text,
    )
    .unwrap();
}
