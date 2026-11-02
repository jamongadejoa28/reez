# Reez Rust Output 0.3.3

EEZ Studio 0.29.0's normal C build runs first. The extension then translates the
actual `.c` outputs with C2Rust 0.22.1. It does not interpret EEZ JSON as UI input.
All C units must be selected and translated; there is no widget/action/variable
allowlist. The original C API names and data layouts are retained through Rust
`extern "C"`, `repr(C)` and unsafe code. This is source translation, not a safe,
idiomatic Rust rewrite or a Rust implementation of LVGL.

Windows requires x64 WSL and Python >=3.11; Cargo in WSL is needed for the default
compile-check. The ZIP bundles the Linux conversion runtime and dependencies.
Linux x64 can run the backend directly. ARM Windows, native Windows without WSL,
macOS, and arbitrary C/C++ inputs are not verified platforms.

## Compiler configuration

```json
{
  "enabled": true,
  "output": "rust-src",
  "compilationDatabase": "build/compile_commands.json",
  "verifyRust": true,
  "wslDistro": ""
}
```

Use your application's real compilation database, with the same LVGL headers,
`lv_conf.h`, includes, defines, target and ABI as the linked LVGL library.
Its entries must cover every `.c` under EEZ's output directory. GCC/Clang-style
commands are accepted; unsupported compiler flags produce an error. Windows
paths in the database are mapped into WSL. Do not copy a database containing
paths from somebody else's PC without regenerating it.

Blank `compilationDatabase` uses a bundled LVGL 9.5 desktop header profile
(32-bit color, CLIB allocation, standard fonts enabled). This is convenient for
PC evaluation. It is not proof of ABI compatibility with a board's LVGL build.
Advanced JSON keys `includeDirectories`, `defines`, `rustToolchain`, `rustTarget`
are passed to the backend; use a compilation database for firmware.

## Output and linking

The output is a Cargo crate: `Cargo.toml`, `Cargo.lock`, `lib.rs`, `src/*.rs`, and
`.reez-c-output.json` recording input/output hashes and compile-check status.
No original UI C file is compiled by the generated crate. Link the translated UI
with your existing C LVGL/drivers, not also with the original C UI definitions.
For a C application, build a static library with `cargo rustc --locked --lib
--crate-type=staticlib` (add your target/profile as required). The default rlib
output can be used directly as a dependency of a Rust application.
An external action or font declared in C remains an external symbol in Rust;
provide its real definition in the application. Header-only callback declarations
do not contain an implementation for a converter to recover.

Generated crates default to `std`. They expose a `std` feature that can be
disabled when used as a dependency of a `no_std` firmware. C2Rust constructs that
require the standard library or unstable Rust still cause errors; no universal
`no_std` or MCU build guarantee is made. Match the C target to the Rust target and
provide platform panic/allocation/linker support. ESP32/STM32 firmware execution
has not been validated by the desktop rendering tests.

C2Rust does not translate C++. An output directory with `.cpp`, `.cc` or `.cxx`
is rejected, including EEZ's C++ Flow runtime. Unsupported C constructs, missing
headers, compilation errors and output collisions are reported in Studio. An
error preserves prior Rust files and suppresses overall success; original C
output may already have been updated. Turning compile-check off is explicit and
is recorded as `rustCompileChecked: false`, not as a compiler pass.

Only files listed in the generated manifest are replaced. User files are
preserved; conflicting filenames and symlink paths are rejected. Builds are
serialized. Save settings in the top toolbar panel; its position remains above
the properties tools. Older executable/args/environment JSON-launcher overrides
are not used by 0.3. WSL distro selection still applies.
