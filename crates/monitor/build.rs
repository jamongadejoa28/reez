use std::{env, fs, path::PathBuf};
fn main() {
    println!("cargo:rerun-if-env-changed=EEZ_PROJECT");
    println!("cargo:rerun-if-env-changed=EEZ_RUST_SRC");
    let out = PathBuf::from(env::var("OUT_DIR").unwrap());
    let dest = out.join("ui");
    if let Some(source) = env::var_os("EEZ_RUST_SRC") {
        let source = PathBuf::from(source)
            .canonicalize()
            .expect("EEZ_RUST_SRC directory");
        let manifest = source.join(".reez-manifest.json");
        println!("cargo:rerun-if-changed={}", manifest.display());
        let manifest: serde_json::Value =
            serde_json::from_slice(&fs::read(&manifest).expect("Studio Rust build manifest"))
                .expect("Rust manifest JSON");
        let files = manifest["files"].as_array().expect("Rust manifest files");
        fs::create_dir_all(&dest).unwrap();
        for name in ["mod.rs", "screens.rs", "styles.rs", "resources.rs"] {
            assert!(
                files.iter().any(|f| f.as_str() == Some(name)),
                "missing generated Rust file {name}"
            );
            let file = source.join(name);
            println!("cargo:rerun-if-changed={}", file.display());
            fs::copy(file, dest.join(name)).expect("copy Studio Rust source");
        }
        println!("cargo:rustc-env=REEZ_UI_ORIGIN=studio-output");
        println!("cargo:rustc-env=REEZ_UI_SOURCE={}", source.display());
    } else {
        let project=PathBuf::from(env::var("EEZ_PROJECT").unwrap_or_else(|_|"/mnt/c/Users/hajun/eez-projects/esp32-s3-monitor-sim/esp32-s3-monitor-sim.eez-project".into()));
        println!("cargo:rerun-if-changed={}", project.display());
        reez::build(&project, &dest, false, &reez::Options::default())
            .expect("generate monitor UI");
        println!("cargo:rustc-env=REEZ_UI_ORIGIN=project-generator");
        println!("cargo:rustc-env=REEZ_UI_SOURCE={}", project.display());
    }
    fs::write(
        out.join("generated.rs"),
        format!("#[path={:?}] pub mod ui;", dest.join("mod.rs")),
    )
    .unwrap();
}
