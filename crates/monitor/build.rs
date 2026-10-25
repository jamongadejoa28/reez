use std::{env, fs, path::PathBuf};
fn main() {
    let root = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap())
        .join("../..")
        .canonicalize()
        .unwrap();
    let project = PathBuf::from(env::var("EEZ_PROJECT").unwrap_or_else(|_| {
        "/mnt/c/Users/hajun/eez-projects/esp32-s3-monitor-sim/esp32-s3-monitor-sim.eez-project"
            .into()
    }));
    println!("cargo:rerun-if-env-changed=EEZ_PROJECT");
    println!("cargo:rerun-if-env-changed=WOKWI_PROJECT");
    println!("cargo:rerun-if-changed={}", project.display());
    let out = PathBuf::from(env::var("OUT_DIR").unwrap());
    let dest = out.join("ui");
    reez::build(&project, &dest, false, &reez::Options::default()).expect("generate monitor UI");
    fs::write(
        out.join("generated.rs"),
        format!("#[path={:?}] pub mod ui;", dest.join("mod.rs")),
    )
    .unwrap();
    let wokwi = PathBuf::from(
        env::var("WOKWI_PROJECT").unwrap_or_else(|_| root.join("../wokwipj").display().to_string()),
    );
    let map = wokwi.join("common/registers.json");
    println!("cargo:rerun-if-changed={}", map.display());
    let values: Vec<serde_json::Value> = serde_json::from_slice(&fs::read(map).unwrap()).unwrap();
    let mut text = String::from("pub static FIELDS: &[Field] = &[\n");
    for v in values {
        let scale = v["scale"].as_i64().unwrap();
        let raw = |k: &str, default: f64| {
            (v[k].as_f64().unwrap_or(default) * scale as f64).round() as i32
        };
        text += &format!(
            "Field{{name:{:?},label:{:?},address:{},scale:{scale},writable:{},stopped_only:{},minimum:{},maximum:{},disable:{}}},\n",
            v["code"].as_str().unwrap(),
            v["nameKo"].as_str().unwrap(),
            v["addr"].as_i64().unwrap() - 1,
            v["writable"].as_bool().unwrap_or(false),
            matches!(
                v["code"].as_str().unwrap(),
                "temp_calib"
                    | "hum_calib"
                    | "hi_temp_set"
                    | "lo_temp_set"
                    | "hi_hum_set"
                    | "lo_hum_set"
                    | "no_humidify_on_cool"
                    | "no_dehumid_on_heat"
                    | "cylinder_foul_hours"
            ),
            raw("min", 0.),
            raw("max", 0.),
            if v["disableValue"].is_number() {
                raw("disableValue", 0.)
            } else {
                -32768
            }
        );
    }
    text += "];";
    fs::write(out.join("fields.rs"), text).unwrap();
}
