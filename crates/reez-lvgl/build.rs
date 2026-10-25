use std::{env, path::PathBuf, process::Command};
fn run(c: &mut Command) {
    assert!(
        c.status().expect("launch native tool").success(),
        "native build failed"
    );
}
fn main() {
    for key in [
        "REEZ_LVGL",
        "REEZ_LV_CONF",
        "REEZ_LVGL_LIB",
        "LIBCLANG_PATH",
    ] {
        println!("cargo:rerun-if-env-changed={key}");
    }
    println!("cargo:rerun-if-changed=lv_conf.h");
    let root = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap())
        .join("../..")
        .canonicalize()
        .unwrap();
    let lvgl = PathBuf::from(
        env::var("REEZ_LVGL")
            .unwrap_or_else(|_| root.join("../wokwipj/.tools/lvgl").display().to_string()),
    );
    let conf = PathBuf::from(env::var("REEZ_LV_CONF").unwrap_or_else(|_| {
        root.join("crates/reez-lvgl/lv_conf.h")
            .display()
            .to_string()
    }));
    assert!(
        lvgl.join("lvgl.h").exists(),
        "set REEZ_LVGL to LVGL 9.5.0 source"
    );
    let version = std::fs::read_to_string(lvgl.join("lv_version.h")).expect("LVGL version header");
    for (key, value) in [("MAJOR", "9"), ("MINOR", "5"), ("PATCH", "0")] {
        let expected = format!("#define LVGL_VERSION_{key} {value}");
        assert!(
            version.lines().any(|line| line.trim() == expected),
            "Reez requires LVGL 9.5.0"
        );
    }
    let out = PathBuf::from(env::var("OUT_DIR").unwrap());
    let desktop = env::var_os("CARGO_FEATURE_DESKTOP").is_some();
    if desktop {
        assert_eq!(
            env::var("HOST"),
            env::var("TARGET"),
            "desktop cross builds need a native C toolchain; build on the host"
        );
        let build = out.join("native");
        run(Command::new("cmake")
            .arg("-S")
            .arg(&lvgl)
            .arg("-B")
            .arg(&build)
            .args([
                "-G",
                "Ninja",
                "-DCMAKE_BUILD_TYPE=Release",
                "-DCONFIG_LV_BUILD_EXAMPLES=OFF",
                "-DCONFIG_LV_BUILD_DEMOS=OFF",
                "-DCONFIG_LV_USE_THORVG_INTERNAL=OFF",
                "-DCONFIG_LV_BUILD_THORVG_INTERNAL=OFF",
            ])
            .arg(format!("-DLV_BUILD_CONF_PATH={}", conf.display())));
        run(Command::new("cmake")
            .arg("--build")
            .arg(&build)
            .args(["--target", "lvgl", "-j", "8"]));
        println!("cargo:rustc-link-search=native={}/lib", build.display());
        println!("cargo:rustc-link-lib=static=lvgl");
        println!("cargo:rustc-link-lib=SDL2");
        println!("cargo:rustc-link-lib=m");
    } else {
        let lib =
            env::var("REEZ_LVGL_LIB").expect("REEZ_LVGL_LIB must contain target-matched liblvgl.a");
        println!("cargo:rustc-link-search=native={lib}");
        println!("cargo:rustc-link-lib=static=lvgl");
    }
    let bindings = bindgen::Builder::default()
        .header(lvgl.join("lvgl.h").to_str().unwrap())
        .clang_arg(format!("-I{}", lvgl.display()))
        .clang_arg(format!("-DLV_CONF_PATH=\"{}\"", conf.display()))
        .clang_arg(format!("--target={}", env::var("TARGET").unwrap()))
        .allowlist_function("lv_.*")
        .allowlist_type("lv_.*")
        .allowlist_var("(LV_|lv_font_).*")
        .prepend_enum_name(false)
        // C documentation contains indented diagrams, not Rust doctests.
        .generate_comments(false)
        .use_core()
        .derive_debug(false)
        .layout_tests(false)
        .parse_callbacks(Box::new(bindgen::CargoCallbacks::new()))
        .generate()
        .expect("LVGL bindings");
    bindings.write_to_file(out.join("bindings.rs")).unwrap();
}
