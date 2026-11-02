# C output backend

The 0.3 extension invokes `integration/c-output-runner.js`, which runs
`integration/backend/convert.py` directly on Linux or through `wsl.exe` on
Windows. Its input is EEZ's completed C output directory, never the EEZ UI JSON.
`integration/index.js` retains the original Studio build and only releases its
success message after Rust generation and the configured compile-check succeed.

C2Rust 0.22.1 parses the C compilation units with Clang. All C units are required;
C++ units are rejected. Opaque C types are lowered to stable Rust pointer-only
opaque types. Nightly-only output is not hidden by RUSTC_BOOTSTRAP. The original
C and headers are hashed and checked again before atomic output publication.
All inputs are reparsed each build so external header changes are not hidden by
an incomplete cache. Cargo uses a shared, incremental, debug-info-free cache at
`~/.cache/reez/c-output/target`.

The ZIP contains the x64 Linux loader, libraries, C2Rust executable, Clang
resource headers, pinned LVGL 9.5 headers, locked support crates and licence/source
notices. Python >=3.11 is supplied by WSL. Cargo is used for the default-on check.
This changes 0.2's prerequisites: it no longer runs solely in Electron/WASI.

Run a request outside Studio:

```json
{
  "operation": "convert",
  "sourceDirectory": "/path/to/eez-c-output",
  "outputDirectory": "/path/to/rust-src",
  "projectDirectory": "/path/to/project",
  "settings": {"compilationDatabase": "/path/to/compile_commands.json", "verifyRust": true}
}
```

```sh
node /path/to/extracted-extension/c-output-runner.js --request request.json
```

`tools/transpile_c_output.py` remains an independent experimental command-line
probe. The installed extension uses `integration/backend/convert.py`.
`crates/reez` and `integration/wasi-runner.js` are the earlier limited JSON
prototype and are not used or installed as the 0.3 build backend.

Validation includes independent C action/global-state/function-pointer/resource
behavior comparisons, C/Rust LVGL rendering comparison, a real Windows Studio
Build, unchanged C outputs, Unicode/space paths and transactional failure tests.
See `artifacts/c-output-validation/` and the tests. Refer to the release's
SUPPORT.md for compiler/ABI and C++ boundaries.
