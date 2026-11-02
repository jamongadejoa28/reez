# EEZ Flow C++ translation probe (2026-10-26)

This is a development record, not a released C++ backend. The shipped Reez
extension still supports C output only and rejects a build that contains C++.

## Input

- EEZ Studio 0.29.0 generated C and C++ from the real
  `esp32-s3-sim-flow.eez-project` sample with Flow enabled.
- Generated files included `eez-flow.cpp`, `eez-flow.h`, `screens.c`, `ui.c`,
  `styles.c`, and `images.c`. The original Studio build completed.
- Clang 23 accepted the generated C++ file with the bundled LVGL headers.

## Translator experiment

- Cpp2Rust commit `1d1fb4c699e738772ff85d35fd4b1e01fddeb4ab` was built
  locally with LLVM/Clang 23.1.5 and Rust 1.99.1.
- The unmodified translator stopped on `long double` and then a standard
  library `std::chrono::duration` alias before emitting source.
- Local diagnostic patches lowered `long double` to `f64`, allowed unrecognized
  system aliases, and emitted declarations for referenced C functions. These
  changes have **not** been reviewed for semantic equivalence and are not
  applied by the released extension.
- With these patches, the translator emitted about 42,000 lines of Rust for
  `eez-flow.cpp`.
- `cargo check` on that output failed. Before the external C declaration
  experiment, there were 477 errors. After that experiment and mechanical
  cleanup of its emitted declarations, 114 errors remained. They include
  missing `std::chrono` types, generated `unsafe impl` blocks targeting Rust
  structs instead of traits for EEZ Flow inheritance, and unresolved external
  symbols. Those are code generation defects, not missing Cargo flags.
- The C2Rust 0.22.1 frontend also fails on this sample's generated `screens.c`
  with an unsupported Clang AST node. The current C-only backend works on
  non-Flow projects.

The generated C++ Rust source is therefore **not compilable or executable**.
No Flow-enabled ZIP should be published until the output compiles, links to
LVGL, and passes a PC GUI behavior test. `libcc2rs` also uses `std`, so even
successful desktop compilation would need further work for MCU targets.

## Reproduce the development probe

`tools/setup_cpp2rust_llvm.py` stages LLVM 23 under ignored `.tools/llvm23`
without installing system packages. The upstream Cpp2Rust checkout and its
local diagnostic modifications are kept under ignored `.tools/cpp2rust`.
Running that script requires `apt-get download`, `dpkg-deb`, network access,
and several gigabytes of free disk space. The output of this probe is not part
of the extension package.
