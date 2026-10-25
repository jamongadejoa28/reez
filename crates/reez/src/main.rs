use std::path::PathBuf;
fn execute() -> Result<(), (i32, reez::Diagnostic)> {
    let mut input = None;
    let mut output = None;
    let mut check = false;
    let mut options = reez::Options::default();
    let mut args = std::env::args().skip(1);
    let bad = |message: String| {
        (
            2,
            reez::Diagnostic {
                path: "arguments".into(),
                message,
            },
        )
    };
    while let Some(a) = args.next() {
        match a.as_str() {
            "--check" => check = true,
            "--help" => {
                println!(
                    "reez --project FILE [--out DIR] [--check] [--font-converter JS] [--node EXE]"
                );
                return Ok(());
            }
            "--version" => {
                println!("reez {}", env!("CARGO_PKG_VERSION"));
                return Ok(());
            }
            "--project" | "--out" | "--font-converter" | "--node" | "--prepared-fonts" => {
                let value = PathBuf::from(
                    args.next()
                        .ok_or_else(|| bad(format!("{a} requires a value")))?,
                );
                match a.as_str() {
                    "--project" => input = Some(value),
                    "--out" => output = Some(value),
                    "--font-converter" => options.font_converter = value,
                    "--prepared-fonts" => options.prepared_fonts = Some(value),
                    _ => options.node = value,
                }
            }
            _ => return Err(bad(format!("unknown argument {a}"))),
        }
    }
    let input = input.ok_or_else(|| bad("--project is required".into()))?;
    let output = output.unwrap_or_else(|| input.parent().unwrap().join("rust-src"));
    let n = reez::build(&input, &output, check, &options).map_err(|e| (1, e))?;
    println!(
        "{}",
        serde_json::json!({"ok":true,"objects":n,"output":output,"check":check})
    );
    Ok(())
}
fn main() {
    if let Err((code, error)) = execute() {
        eprintln!("{}", serde_json::to_string(&error).unwrap());
        std::process::exit(code);
    }
}
