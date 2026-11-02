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
        env, windowsHide: true, maxBuffer: 16 * 1024 * 1024, timeout: 600000
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
    const c = { enabled:false, output:"rust-src", compilerProfile:"bundled-lvgl-9.5", compilationDatabase:"", verifyRust:true, wslDistro:"", ...value };
    if (typeof c.enabled !== "boolean") throw new Error("reez.json: enabled must be true or false");
    if (typeof c.output !== "string" || !c.output.trim()) throw new Error("reez.json: output must be a folder name");
    if(typeof c.compilationDatabase!=="string" || typeof c.wslDistro!=="string" || typeof c.verifyRust!=="boolean")throw new Error("Invalid C backend configuration");
    return c;
}
function writeSettings(projectFile, changes) {
    const c = { ...readSettings(projectFile), enabled: !!changes.enabled, output: changes.output.trim() };
    for(const key of ["compilationDatabase","compilerProfile","verifyRust","wslDistro"]) if(key in changes)c[key]=changes[key];
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
    const runner = path.join(__dirname, "c-output-runner.js");
    if (!fs.existsSync(runner) || !fs.existsSync(path.join(__dirname,"backend","runtime","bin","c2rust-transpile"))) {
        throw new Error("The C conversion backend is missing. Install the complete Reez extension ZIP.");
    }
    return { executable: process.execPath, args: [runner], environment: { ELECTRON_RUN_AS_NODE:"1", NODE_NO_WARNINGS:"1" } };
}
function config(projectFile) {
    const settings=readSettings(projectFile);
    if(!settings.enabled)return null;
    return { ...settings, ...nativeRuntime() };
}
async function invokeBackend(request) {
    const runtime=nativeRuntime();
    const os=require("os");const work=fs.mkdtempSync(path.join(os.tmpdir(),"reez-c-request-"));
    try {
        const file=path.join(work,"request.json");fs.writeFileSync(file,JSON.stringify(request));
        return await exec(runtime.executable,[...runtime.args,"--request",file],{...process.env,...runtime.environment});
    } finally {fs.rmSync(work,{recursive:true,force:true});}
}
async function checkInstallation(projectFile) {
    const report = JSON.parse((await invokeBackend({operation:"check",settings:readSettings(projectFile)})).trim());
    const version = JSON.parse(fs.readFileSync(path.join(__dirname,"package.json"),"utf8")).version;
    if (report.version !== version) throw new Error(`Reez adapter ${version} and backend ${report.version} differ. Close EEZ Studio, reinstall the complete ZIP, then reopen it.`);
    return JSON.stringify({extensionVersion:version,adapterPath:__dirname,...report});
}
async function generate(store, snapshot, c) {
    const base=path.dirname(store.filePath);
    const source=path.resolve(base,store.project.settings.build.destinationFolder || ".");
    const output=path.resolve(base,c.output || "rust-src");
    const nested=(a,b)=>{const relative=path.relative(a,b);return relative==="" || (!relative.startsWith(".."+path.sep)&&relative!==".."&&!path.isAbsolute(relative));};
    if(nested(source,output)||nested(output,source)||nested(output,base))throw new Error("Rust output must be separate from the project and C output directories");
    return await invokeBackend({operation:"convert",sourceDirectory:source,outputDirectory:output,projectDirectory:base,settings:c});
}
function registerFolderUninstall() {
    // Studio 0.29 treats every Project Editor extension as a Yarn package at
    // uninstall time, including a ZIP imported into the user extensions folder.
    // Correct that one case while preserving Yarn's behavior for npm installs.
    const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,"package.json"),"utf8"));
    const folders=require("eez-studio-shared/extensions/extension-folder");
    const registry=require("eez-studio-shared/extensions/extensions");
    const yarn=require("eez-studio-shared/extensions/yarn");
    if(typeof yarn.yarnUninstall!=="function")throw new Error("Unsupported EEZ Studio extension manager");
    const destination=path.resolve(folders.getExtensionFolderPath(manifest.id));
    const previous=yarn.yarnUninstall;
    async function uninstall(name) {
        const installed=registry.extensions.get(manifest.id);
        if(name!==manifest.name || !installed?.installationFolderPath ||
           path.resolve(installed.installationFolderPath)!==destination)return previous(name);
        const current=JSON.parse(fs.readFileSync(path.join(destination,"package.json"),"utf8"));
        if(current.id!==manifest.id || current.name!==manifest.name)throw new Error("Reez extension folder identity changed; refusing to remove it");
        await fs.promises.rm(destination,{recursive:true,force:true});
        for(const filename of Object.keys(require.cache||{})) {
            const relative=path.relative(destination,filename);
            if(relative==="" || (relative!==".." && !relative.startsWith(".."+path.sep) && !path.isAbsolute(relative)))delete require.cache[filename];
        }
        if(yarn.yarnUninstall===uninstall)yarn.yarnUninstall=previous;
    }
    yarn.yarnUninstall=uninstall;
    return ()=>{if(yarn.yarnUninstall===uninstall)yarn.yarnUninstall=previous;};
}
function install() {
    if (process.type !== "renderer") return;
    const build = require("project-editor/build/build");
    if (build.build.__reez) {
        const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,"package.json"),"utf8"));
        const registry=require("eez-studio-shared/extensions/extensions");
        const previous=registry.extensions.get(manifest.id);
        if(previous?.version===manifest.version && previous.installationFolderPath &&
           path.resolve(previous.installationFolderPath)===path.resolve(__dirname))return;
        if(previous?.version && previous.version.localeCompare(manifest.version,undefined,{numeric:true})>0)
            throw new Error(`A newer Reez adapter ${previous.version} is already active; remove duplicate installations`);
        if(typeof previous?.destroy!=="function")throw new Error("An older Reez adapter is active but cannot be replaced; close Studio and run the Reez installer");
        previous.destroy();
        if(build.build.__reez)throw new Error("The previous Reez build hook is still active; close Studio and remove duplicate installations");
    }
    const undoFolderUninstall=registerFolderUninstall();
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
            const report=JSON.parse(summary);
            write.call(output, storeModule.Section.OUTPUT, MessageType.INFO,
                `Rust output: ${report.outputDirectory} (${report.translationUnits} C files; Rust compile-check: ${report.rustCompileChecked ? "passed" : "disabled"})`);
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
    restore = () => { if (build.build === combined) build.build = original; undoFolderUninstall(); };
    const api = { version: JSON.parse(fs.readFileSync(path.join(__dirname, "package.json"), "utf8")).version, config, readSettings, writeSettings, checkInstallation, generate };
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
