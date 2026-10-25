// GPL-3.0-only
"use strict";
exports.mount = function mount(api) {
    const id = "reez-output-panel";
    if (document.getElementById(id)) return { destroy() {} };
    function element(tag, text, css) {
        const e = document.createElement(tag);
        if (text) e.textContent = text;
        if (css) Object.assign(e.style, css);
        return e;
    }
    function project() {
        return require("home/tabs-store").tabs?.activeTab?.projectStore;
    }
    const host = element("div", "", { position: "fixed", right: "18px", top: "43px", zIndex: "10000", font: "13px system-ui, sans-serif" });
    host.id = id;
    const toggle = element("button", "Rust output", { background: "#26394d", color: "#fff", border: "1px solid #608097", borderRadius: "5px", padding: "6px 12px", cursor: "pointer" });
    toggle.type = "button";
    host.append(toggle);
    let dialog = null;
    function close() { if (dialog) dialog.remove(); dialog = null; }
    toggle.onclick = () => {
        close();
        const store = project();
        dialog = element("div", "", { width: "340px", marginTop: "6px", padding: "18px", background: "#182433", color: "#fff", border: "1px solid #608097", borderRadius: "6px", boxShadow: "0 8px 24px #0008" });
        dialog.setAttribute("role", "dialog");
        dialog.setAttribute("aria-label", "Reez Rust output settings");
        dialog.append(element("strong", "Reez Rust Output " + api.version));
        host.append(dialog);
        if (!store?.filePath) { dialog.append(element("p", "Open and save an EEZ project first.")); return; }
        dialog.append(element("p", store.filePath.split(/[\\/]/).pop(), { overflowWrap: "anywhere" }));
        const status = element("p", "", { whiteSpace: "pre-wrap", overflowWrap: "anywhere" });
        let settings;
        try { settings = api.readSettings(store.filePath); } catch (error) { status.textContent = error.message; dialog.append(status); return; }
        const label = element("label", "");
        const enabled = element("input"); enabled.type = "checkbox"; enabled.checked = settings.enabled;
        label.append(enabled, document.createTextNode(" Enable Rust output for this project")); dialog.append(label);
        const folderLabel = element("label", "Output folder", { display: "block", marginTop: "14px" });
        const folder = element("input", "", { display: "block", width: "100%", marginTop: "5px", boxSizing: "border-box", padding: "6px" });
        folder.type = "text"; folder.value = settings.output; folderLabel.append(folder); dialog.append(folderLabel);
        dialog.append(element("p", "Build will create C/C++ and Rust outputs. LVGL 9.5.0 without EEZ Flow is supported."));
        const check = element("button", "Check installation"); check.type = "button";
        check.onclick = async () => { check.disabled = true; status.textContent = "Checking…"; try { status.textContent = await api.checkInstallation(store.filePath); } catch (e) { status.textContent = e.message; } finally { check.disabled = false; } };
        const save = element("button", "Save", { marginLeft: "8px" }); save.type = "button";
        save.onclick = () => { try { api.writeSettings(store.filePath, { enabled: enabled.checked, output: folder.value }); status.textContent = "Saved. Use the normal Build button."; update(); } catch (e) { status.textContent = e.message; } };
        const dismiss = element("button", "Close", { marginLeft: "8px" }); dismiss.type = "button"; dismiss.onclick = close;
        dialog.append(check, save, dismiss, status);
    };
    function update() {
        const store = project();
        try { toggle.textContent = "Rust output · " + (store?.filePath && api.readSettings(store.filePath).enabled ? "ON" : "OFF"); }
        catch (_) { toggle.textContent = "Rust output · settings error"; }
    }
    document.body.append(host);
    update();
    const timer = setInterval(update, 1500);
    timer.unref?.();
    return { destroy() { clearInterval(timer); host.remove(); } };
};
