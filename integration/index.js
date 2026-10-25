// GPL-3.0-only: this adapter loads EEZ Studio GPL modules at runtime.
"use strict";
const fs = require("fs");
const path = require("path");
const cp = require("child_process");
let active = false;
let restore = null;
let panel = null;
function exec(file, args, env = process.env) {
    return new Promise((resolve, reject) => cp.execFile(file, args, {
        env, windowsHide: true, maxBuffer: 4 * 1024 * 1024, timeout: 120000
    }, (err, stdout, stderr) => {
        if (err) reject(new Error(`Rust generation failed: ${stderr || err.message}`));
        else resolve(stdout);
    }));
}
function settingsPath(projectFile) {
    return path.join(path.dirname(projectFile), "reez.json");
}
function readSettings(projectFile) {
    const file = settingsPath(projectFile);
    const value = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : {};
    if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("reez.json must be a JSON object");
    const c = { enabled: false, output: "rust-src", ...value };
    if (typeof c.enabled !== "boolean") throw new Error("reez.json: enabled must be true or false");
    if (typeof c.output !== "string" || !c.output.trim()) throw new Error("reez.json: output must be a folder name");
    if (c.args && (!Array.isArray(c.args) || c.args.some(v => typeof v !== "string"))) throw new Error("reez.json: args must be a string array");
    return c;
}
function writeSettings(projectFile, changes) {
    const c = { ...readSettings(projectFile), enabled: !!changes.enabled, output: changes.output.trim() };
    if (!c.output) throw new Error("Output folder is required");
    const target = settingsPath(projectFile);
    const temp = `${target}.${process.pid}-${Date.now()}.tmp`;
    try {
        fs.writeFileSync(temp, JSON.stringify(c, null, 2) + "\n", { flag: "wx" });
        fs.renameSync(temp, target);
    } finally { if (fs.existsSync(temp)) fs.unlinkSync(temp); }
    return c;
}
function nativeRuntime() {
    const wasm = path.join(__dirname, "bin", "reez.wasm");
    if (!fs.existsSync(wasm)) throw new Error("Reez Rust generator is missing. Install the complete Reez extension ZIP.");
    const converter = path.join(__dirname, "node_modules", "lv_font_conv", "lv_font_conv.js");
    if (!fs.existsSync(converter)) throw new Error("Reez font converter is missing. Reinstall the complete extension ZIP.");
    return {
        executable: process.execPath, args: [path.join(__dirname, "wasi-runner.js")],
        environment: { ELECTRON_RUN_AS_NODE: "1", NODE_NO_WARNINGS: "1" }
    };
}
function config(projectFile) {
    const c = readSettings(projectFile);
    if (!c.enabled) return null;
    if (c.executable) return c; // Preserve explicitly configured native or WSL launchers.
    const runtime = nativeRuntime();
    return { ...c, ...runtime, environment: { ...c.environment, ...runtime.environment } };
}
async function checkInstallation(projectFile) {
    const saved = readSettings(projectFile);
    const c = saved.executable ? saved : nativeRuntime();
    const result = await exec(c.executable, [...(c.args || []), "--version"], { ...process.env, ...c.environment });
    return result.trim();
}
async function generate(store, snapshot, c) {
    const base = path.dirname(store.filePath);
    const output = path.resolve(base, c.output || "rust-src");
    const existingOutput = path.resolve(base, store.project.settings.build.destinationFolder || ".");
    const nested = (a, b) => { const rel = path.relative(a, b); return rel === "" || (!rel.startsWith(".." + path.sep) && rel !== ".." && !path.isAbsolute(rel)); };
    if (nested(existingOutput, output) || nested(output, existingOutput) || nested(output, base)) throw new Error("Rust output must be separate from the project and C output directories");
    const file = path.join(base, `.reez-${process.pid}-${Date.now()}.eez-project`);
    fs.writeFileSync(file, snapshot, { flag: "wx" });
    try {
        let inputArg = file, outputArg = output;
        if (c.wslDistro) {
            const toWsl = async p => (await exec("wsl.exe", ["-d", c.wslDistro, "--exec", "wslpath", "-u", p])).trim();
            inputArg = await toWsl(file); outputArg = await toWsl(output);
        }
        return await exec(c.executable, [...(c.args || []), "--project", inputArg, "--out", outputArg], { ...process.env, ...(c.environment || {}) });
    } finally { fs.unlinkSync(file); }
}
function install() {
    if (process.type !== "renderer") return;
    const build = require("project-editor/build/build");
    if (build.build.__reez) return;
    const storeModule = require("project-editor/store");
    const { MessageType } = require("project-editor/core/object");
    const original = build.build;
    async function combined(store, option) {
        if (option !== "buildFiles" || !store.filePath) return original(store, option);
        const output = store.outputSectionsStore;
        let c;
        try { c = config(store.filePath); } catch (err) {
            output.clear(storeModule.Section.OUTPUT);
            output.write(storeModule.Section.OUTPUT, MessageType.ERROR, `Reez: ${err.message}`);
            return;
        }
        if (!c) return original(store, option);
        if (active) { output.write(storeModule.Section.OUTPUT, MessageType.ERROR, "Reez: build already running"); return; }
        active = true;
        const write = output.write;
        const success = [];
        try {
            const snapshot = storeModule.getJSON(store, 0);
            output.write = function (...args) {
                if (typeof args[2] === "string" && args[2].startsWith("Build successfully finished")) { success.push(args); return; }
                return write.apply(this, args);
            };
            const result = await original(store, option);
            if (output.getSection(storeModule.Section.OUTPUT).numErrors) return result;
            output.setLoading(storeModule.Section.OUTPUT, true);
            if (storeModule.getJSON(store, 0) !== snapshot) throw new Error("Project changed during C build; rebuild to generate matching outputs");
            const summary = await generate(store, snapshot, c);
            write.call(output, storeModule.Section.OUTPUT, MessageType.INFO, `Rust output: ${summary.trim()}`);
            for (const args of success) write.apply(output, args);
            return result;
        } catch (err) {
            write.call(output, storeModule.Section.OUTPUT, MessageType.ERROR, `Reez: ${err.message}`);
        } finally {
            output.write = write;
            output.setLoading(storeModule.Section.OUTPUT, false);
            active = false;
        }
    }
    combined.__reez = true;
    build.build = combined;
    restore = () => { if (build.build === combined) build.build = original; };
    const api = { version: "0.2.0", config, readSettings, writeSettings, checkInstallation, generate };
    window.reezOutput = api;
    if (typeof document !== "undefined") panel = require("./panel").mount(api);
}
function destroy() {
    if (restore) restore();
    if (panel) panel.destroy();
    restore = panel = null;
    if (typeof window !== "undefined") delete window.reezOutput;
}
exports.default = { preInstalled: false, extensionType: "pext", init: install, destroy };
Object.assign(exports, { install, destroy, config, readSettings, writeSettings, nativeRuntime, checkInstallation, generate });
