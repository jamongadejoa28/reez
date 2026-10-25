# Reez Rust Output 0.2.0

Tested integration: EEZ Studio 0.29.0, LVGL 9.5.0, Windows x64. The extension ZIP contains a portable Rust WebAssembly
generator. Windows is the primary tested Studio platform for this release.

The generated UI is Rust source that calls the existing C LVGL library through
`reez-lvgl`. It requires target-matched headers and `lv_conf.h` when compiling
firmware. Installing this extension generates source files; it does not install
board toolchains or compile ESP32/STM32 firmware.

Supported: screen, container, button, label, coordinates, literal text and flags,
local styles used by the sample, single-source fonts embedded as Rust bytes.
Unsupported features fail explicitly: EEZ Flow, declared actions/variables,
expressions, images, project imports, user widgets, shared/conditional styles,
input groups. Existing projects are opt-in through the Rust output panel.

A project uses this portable configuration next to its .eez-project file:

```json
{"enabled": true, "output": "rust-src"}
```

No username, absolute generator path, MCP token, or WSL distribution is needed.
Advanced users may retain the older executable/args/environment/wslDistro keys;
these override the bundled WebAssembly generator.

"Check installation" displays the generator version. No Rust, Node.js, Python, or WSL installation is required. Build failures appear in
Studio's Output panel. A Rust failure preserves the previous Rust output and
suppresses the overall build-success message. Existing C output may already
have been updated. Generation is serialized and rejects project changes during
the C build to avoid publishing mismatched versions.

Uninstalling the extension leaves project configuration and generated sources.
Only delete the reez-rust-output extension folder, never the whole extensions
folder. Save work and close Studio before manual replacement or removal.
