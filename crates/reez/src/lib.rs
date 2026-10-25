//! EEZ project → validated intermediate representation → Rust source.
use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet},
    fmt::Write as _,
    fs,
    path::{Path, PathBuf},
    process::Command,
};
#[derive(Debug, Serialize)]
pub struct Diagnostic {
    pub path: String,
    pub message: String,
}
pub type Result<T> = std::result::Result<T, Diagnostic>;
fn err<T>(path: impl Into<String>, message: impl Into<String>) -> Result<T> {
    Err(Diagnostic {
        path: path.into(),
        message: message.into(),
    })
}
fn io(e: impl std::fmt::Display) -> Diagnostic {
    Diagnostic {
        path: "filesystem".into(),
        message: e.to_string(),
    }
}
fn s<'a>(v: &'a Value, key: &str) -> &'a str {
    v[key].as_str().unwrap_or("")
}
fn array<'a>(v: &'a Value, key: &str) -> &'a [Value] {
    v[key].as_array().map(Vec::as_slice).unwrap_or(&[])
}
fn ident(name: &str) -> String {
    let mut n = String::from("o_");
    for c in name.chars() {
        if c.is_ascii_alphanumeric() || c == '_' {
            n.push(c.to_ascii_lowercase())
        } else {
            write!(n, "u{:x}_", c as u32).unwrap();
        }
    }
    n
}
fn rs_string(s: &str) -> String {
    format!("{s:?}")
}
#[derive(Debug)]
pub struct Project {
    pub nodes: Vec<Node>,
    pub pages: Vec<(String, String)>,
    pub fonts: Vec<Value>,
    pub source: Value,
}
#[derive(Debug)]
pub struct Node {
    pub id: String,
    pub parent: Option<String>,
    pub kind: String,
    pub path: String,
    pub props: Value,
}
pub fn parse(source: Value) -> Result<Project> {
    let general = &source["settings"]["general"];
    if s(general, "projectType") != "lvgl" || s(general, "lvglVersion") != "9.5.0" {
        return err("settings.general", "requires LVGL 9.5.0 project");
    }
    if general["flowSupport"].as_bool() == Some(true) {
        return err("settings.general.flowSupport", "EEZ Flow is not supported");
    }
    for (path, v) in [
        ("actions", &source["actions"]),
        ("userWidgets", &source["userWidgets"]),
        ("bitmaps", &source["bitmaps"]),
        (
            "variables.globalVariables",
            &source["variables"]["globalVariables"],
        ),
        ("variables.structures", &source["variables"]["structures"]),
        ("variables.enums", &source["variables"]["enums"]),
        ("lvglStyles.styles", &source["lvglStyles"]["styles"]),
        ("lvglGroups.groups", &source["lvglGroups"]["groups"]),
        ("settings.general.imports", &general["imports"]),
    ] {
        if v.as_array().is_some_and(|v| !v.is_empty()) {
            return err(
                path,
                "feature is not supported by this version; use application-owned Rust callbacks/state",
            );
        }
    }
    let mut p = Project {
        nodes: vec![],
        pages: vec![],
        fonts: array(&source, "fonts").to_vec(),
        source: source.clone(),
    };
    let mut names = BTreeSet::new();
    for (i, page) in array(&source, "userPages").iter().enumerate() {
        let path = format!("userPages[{i}]");
        let components = array(page, "components");
        if components.len() != 1 || s(&components[0], "type") != "LVGLScreenWidget" {
            return err(path, "each page must have one LVGL screen");
        }
        let id = walk(
            &components[0],
            None,
            &format!("{path}.components[0]"),
            &mut p.nodes,
            &mut names,
        )?;
        p.pages.push((s(page, "name").into(), id));
    }
    if p.pages.is_empty() {
        return err("userPages", "no screens");
    }
    let mut fonts = BTreeSet::new();
    for (i, font) in p.fonts.iter().enumerate() {
        if !fonts.insert(s(font, "name").to_owned()) {
            return err(format!("fonts[{i}]"), "duplicate font name");
        }
        if !array(font, "lvglAdditionalSources").is_empty() {
            return err(
                format!("fonts[{i}]"),
                "additional font sources are not supported",
            );
        }
    }
    for n in &p.nodes {
        for states in n.props["localStyles"]["definition"]
            .as_object()
            .into_iter()
            .flat_map(|x| x.values())
        {
            for props in states.as_object().into_iter().flat_map(|x| x.values()) {
                if let Some(font) = props["text_font"].as_str()
                    && !fonts.contains(font)
                    && !matches!(font, "MONTSERRAT_18" | "MONTSERRAT_40" | "MONTSERRAT_48")
                {
                    return err(&n.path, format!("unavailable font {font}"));
                }
            }
        }
    }
    Ok(p)
}
fn walk(
    v: &Value,
    parent: Option<String>,
    path: &str,
    nodes: &mut Vec<Node>,
    names: &mut BTreeSet<String>,
) -> Result<String> {
    const KEYS: &[&str] = &[
        "objID",
        "type",
        "identifier",
        "left",
        "top",
        "width",
        "height",
        "leftUnit",
        "topUnit",
        "widthUnit",
        "heightUnit",
        "children",
        "customInputs",
        "customOutputs",
        "style",
        "timeline",
        "eventHandlers",
        "widgetFlags",
        "states",
        "hiddenFlag",
        "hiddenFlagType",
        "clickableFlag",
        "clickableFlagType",
        "checkedState",
        "checkedStateType",
        "disabledState",
        "disabledStateType",
        "localStyles",
        "groupIndex",
        "text",
        "textType",
        "longMode",
        "recolor",
        "useStaticText",
        "description",
    ];
    for key in v
        .as_object()
        .ok_or_else(|| io("widget must be an object"))?
        .keys()
    {
        if !KEYS.contains(&key.as_str()) {
            return err(format!("{path}.{key}"), "unsupported widget property");
        }
    }
    let kind = s(v, "type");
    if !matches!(
        kind,
        "LVGLScreenWidget" | "LVGLLabelWidget" | "LVGLButtonWidget" | "LVGLContainerWidget"
    ) {
        return err(path, format!("unsupported widget {kind}"));
    }
    let raw = s(v, "identifier");
    let id = if raw.is_empty() {
        ident(path)
    } else {
        ident(raw)
    };
    if !names.insert(id.clone()) {
        return err(path, format!("identifier collision: {raw}"));
    }
    for key in ["customInputs", "customOutputs", "timeline", "eventHandlers"] {
        if !array(v, key).is_empty() {
            return err(format!("{path}.{key}"), "not supported");
        }
    }
    for key in [
        "textType",
        "hiddenFlagType",
        "clickableFlagType",
        "checkedStateType",
        "disabledStateType",
    ] {
        if !matches!(s(v, key), "" | "literal") {
            return err(
                format!("{path}.{key}"),
                "expressions require an unsupported EEZ runtime",
            );
        }
    }
    if v["recolor"].as_bool() == Some(true) {
        return err(path, "label recolor is not supported");
    }
    if !matches!(s(&v["style"], "useStyle"), "" | "default")
        || !array(&v["style"], "conditionalStyles").is_empty()
        || !array(&v["style"], "childStyles").is_empty()
    {
        return err(path, "shared/conditional styles are not supported");
    }
    for key in ["left", "top", "width", "height"] {
        if v[key]
            .as_i64()
            .and_then(|n| i32::try_from(n).ok())
            .is_none()
        {
            return err(format!("{path}.{key}"), "expected i32 coordinate");
        }
        if !matches!(s(v, &format!("{key}Unit")), "" | "px" | "%" | "content") {
            return err(path, "unsupported coordinate unit");
        }
    }
    for key in ["widgetFlags", "states"] {
        for flag in s(v, key).split('|').filter(|x| !x.is_empty()) {
            if !(if key == "widgetFlags" {
                FLAGS.contains(&flag)
            } else {
                STATES.contains(&flag)
            }) {
                return err(path, "invalid flag/state");
            }
        }
    }
    if s(v, "text").contains('\0') {
        return err(path, "label contains NUL");
    }
    if !matches!(
        s(v, "longMode"),
        "" | "WRAP" | "DOT" | "SCROLL" | "SCROLL_CIRCULAR" | "CLIP"
    ) {
        return err(path, "unknown label long mode");
    }
    for (part, states) in v["localStyles"]["definition"]
        .as_object()
        .into_iter()
        .flatten()
    {
        if !matches!(
            part.as_str(),
            "MAIN" | "SCROLLBAR" | "INDICATOR" | "KNOB" | "ITEMS"
        ) {
            return err(path, format!("unsupported part {part}"));
        }
        for (state, props) in states.as_object().into_iter().flatten() {
            if !state.split('|').all(|x| {
                matches!(
                    x,
                    "DEFAULT"
                        | "CHECKED"
                        | "PRESSED"
                        | "DISABLED"
                        | "FOCUSED"
                        | "FOCUS_KEY"
                        | "EDITED"
                        | "HOVERED"
                        | "USER_1"
                        | "USER_2"
                        | "USER_3"
                        | "USER_4"
                )
            }) {
                return err(path, "unsupported style state");
            }
            for (key, val) in props.as_object().into_iter().flatten() {
                style_value(key, val, path)?;
            }
        }
    }
    nodes.push(Node {
        id: id.clone(),
        parent,
        kind: kind.into(),
        path: path.into(),
        props: v.clone(),
    });
    for (i, child) in array(v, "children").iter().enumerate() {
        walk(
            child,
            Some(id.clone()),
            &format!("{path}.children[{i}]"),
            nodes,
            names,
        )?;
    }
    Ok(id)
}
const FLAGS: &[&str] = &[
    "CLICKABLE",
    "CLICK_FOCUSABLE",
    "CHECKABLE",
    "SCROLLABLE",
    "SCROLL_ELASTIC",
    "SCROLL_MOMENTUM",
    "SCROLL_ONE",
    "SCROLL_CHAIN_HOR",
    "SCROLL_CHAIN_VER",
    "SCROLL_ON_FOCUS",
    "SCROLL_WITH_ARROW",
    "SNAPPABLE",
    "PRESS_LOCK",
    "EVENT_BUBBLE",
    "GESTURE_BUBBLE",
    "ADV_HITTEST",
    "IGNORE_LAYOUT",
    "FLOATING",
    "HIDDEN",
];
const STATES: &[&str] = &[
    "DEFAULT",
    "CHECKED",
    "PRESSED",
    "DISABLED",
    "FOCUSED",
    "FOCUS_KEY",
    "EDITED",
    "HOVERED",
    "USER_1",
    "USER_2",
    "USER_3",
    "USER_4",
];
fn style_value(key: &str, val: &Value, path: &str) -> Result<String> {
    Ok(match key {
        "text_color" | "bg_color" | "border_color" | "outline_color" | "shadow_color" => {
            let c = val.as_str().unwrap_or("");
            if c.len() != 7 || !c.starts_with('#') || !c[1..].bytes().all(|b| b.is_ascii_hexdigit())
            {
                return err(path, "expected #rrggbb color");
            }
            format!("reez_lvgl::color(0x{})", &c[1..])
        }
        "text_font" => {
            let n = val.as_str().ok_or_else(|| io("invalid font"))?;
            if n.starts_with("MONTSERRAT_") {
                format!("&lv_font_{}", n.to_lowercase())
            } else {
                format!("font_{}", ident(n))
            }
        }
        "text_align" => {
            let n = val.as_str().unwrap_or("");
            if !matches!(n, "AUTO" | "LEFT" | "CENTER" | "RIGHT") {
                return err(path, "invalid text alignment");
            }
            format!("LV_TEXT_ALIGN_{n}")
        }
        "border_width" | "radius" | "pad_left" | "pad_right" | "pad_top" | "pad_bottom"
        | "pad_row" | "pad_column" | "bg_opa" | "text_opa" | "opa" | "border_opa"
        | "shadow_width" | "shadow_spread" | "shadow_offset_x" | "shadow_offset_y"
        | "text_letter_space" | "text_line_space" | "outline_width" | "outline_pad" => val
            .as_i64()
            .filter(|n| i32::try_from(*n).is_ok())
            .ok_or_else(|| Diagnostic {
                path: path.into(),
                message: format!("invalid style value {key}"),
            })?
            .to_string(),
        _ => return err(path, format!("unsupported style property {key}")),
    })
}
pub struct Options {
    pub node: PathBuf,
    pub font_converter: PathBuf,
    pub prepared_fonts: Option<PathBuf>,
}
impl Default for Options {
    fn default() -> Self {
        Self {
            prepared_fonts: None,
            node: std::env::var_os("REEZ_NODE")
                .map(PathBuf::from)
                .unwrap_or_else(|| "node".into()),
            font_converter: std::env::var_os("REEZ_FONT_CONVERTER")
                .map(PathBuf::from)
                .unwrap_or_else(|| {
                    for start in [std::env::current_exe().ok(), std::env::current_dir().ok()]
                        .into_iter()
                        .flatten()
                    {
                        for directory in start.ancestors().take(8) {
                            let bundled =
                                directory.join("node_modules/lv_font_conv/lv_font_conv.js");
                            if bundled.is_file() {
                                return bundled;
                            }
                        }
                    }
                    PathBuf::from("node_modules/lv_font_conv/lv_font_conv.js")
                }),
        }
    }
}
fn coord(v: &Value, key: &str) -> String {
    match s(v, &format!("{key}Unit")) {
        "%" => format!("reez_lvgl::pct({})", v[key]),
        "content" => "LV_SIZE_CONTENT as i32".into(),
        _ => v[key].to_string(),
    }
}
pub fn generate(p: &Project, base: &Path, options: &Options) -> Result<BTreeMap<String, String>> {
    let mut resources =
        String::from("// Generated by reez. Do not edit.\n#![allow(non_upper_case_globals)]\n");
    let temp = if let Some(directory) = &options.prepared_fonts {
        tempfile::tempdir_in(directory)
    } else {
        tempfile::tempdir()
    }
    .map_err(io)?;
    for (index, font) in p.fonts.iter().enumerate() {
        let name = ident(s(font, "name"));
        let bytes = if let Some(directory) = &options.prepared_fonts {
            fs::read(directory.join(format!("{index}.bin"))).map_err(io)?
        } else {
            let file = temp.path().join(format!("{name}.ttf"));
            let bin = temp.path().join(format!("{name}.bin"));
            if let Some(encoded) = font["embeddedFontFile"].as_str().filter(|s| !s.is_empty()) {
                let encoded = encoded.split_once(",").map(|(_, b)| b).unwrap_or(encoded);
                fs::write(
                    &file,
                    base64::engine::general_purpose::STANDARD
                        .decode(encoded)
                        .map_err(io)?,
                )
                .map_err(io)?;
            } else {
                fs::copy(
                    base.join(s(&font["source"], "filePath").replace('\\', "/")),
                    &file,
                )
                .map_err(io)?;
            }
            let output = Command::new(&options.node)
                .arg(&options.font_converter)
                .args(["--font"])
                .arg(&file)
                .args([
                    "--size",
                    &font["source"]["size"].to_string(),
                    "--bpp",
                    &font["bpp"].to_string(),
                    "--range",
                    s(font, "lvglRanges"),
                    "--symbols",
                    s(font, "lvglSymbols"),
                    "--format",
                    "bin",
                    "--no-compress",
                    "--output",
                ])
                .arg(&bin)
                .output()
                .map_err(io)?;
            if !output.status.success() {
                return err(
                    format!("fonts.{}", s(font, "name")),
                    String::from_utf8_lossy(&output.stderr),
                );
            }
            fs::read(bin).map_err(io)?
        };
        writeln!(resources, "pub static FONT_{name}: &[u8] = &{bytes:?};").unwrap();
    }
    let mut screens = String::from(
        "// Generated by reez. Do not edit.\nuse reez_lvgl::sys::*;\nuse core::ptr::null_mut;\nextern crate alloc;\nuse self::alloc::{rc::Rc,vec::Vec};\nuse core::marker::PhantomData;\npub struct Ui {\n",
    );
    for n in &p.nodes {
        writeln!(screens, "pub {}: *mut lv_obj_t,", n.id).unwrap();
    }
    screens.push_str("fonts: Vec<*mut lv_font_t>, _thread: PhantomData<Rc<()>>,\n}\nimpl Ui {\n/// # Safety\n/// Call once per instance on the initialized LVGL thread. Keep the display alive until drop.\n#[allow(unsafe_op_in_unsafe_fn)]\npub unsafe fn create() -> Self {\nlet mut fonts=Vec::new();\n");
    for f in &p.fonts {
        let n = ident(s(f, "name"));
        writeln!(screens,"let font_{n}=lv_binfont_create_from_buffer(super::resources::FONT_{n}.as_ptr() as *mut _,super::resources::FONT_{n}.len() as u32);\nassert!(!font_{n}.is_null(),\"font load failed\");fonts.push(font_{n});").unwrap();
    }
    let mut styles = String::from("// Generated by reez. Do not edit.\nuse reez_lvgl::sys::*;\n");
    for n in &p.nodes {
        let ctor = match n.kind.as_str() {
            "LVGLLabelWidget" => "lv_label_create",
            "LVGLButtonWidget" => "lv_button_create",
            _ => "lv_obj_create",
        };
        writeln!(screens,"let {}={ctor}({});assert!(!{}.is_null());\nlv_obj_set_pos({}, {}, {});lv_obj_set_size({}, {}, {});",n.id,n.parent.as_deref().unwrap_or("null_mut()"),n.id,n.id,coord(&n.props,"left"),coord(&n.props,"top"),n.id,coord(&n.props,"width"),coord(&n.props,"height")).unwrap();
        // Match Studio's serialized flags, while preserving class-private flags.
        let flags = [
            "CLICKABLE",
            "CLICK_FOCUSABLE",
            "CHECKABLE",
            "SCROLLABLE",
            "SCROLL_ELASTIC",
            "SCROLL_MOMENTUM",
            "SCROLL_ONE",
            "SCROLL_CHAIN_HOR",
            "SCROLL_CHAIN_VER",
            "SCROLL_ON_FOCUS",
            "SCROLL_WITH_ARROW",
            "SNAPPABLE",
            "PRESS_LOCK",
            "EVENT_BUBBLE",
            "GESTURE_BUBBLE",
            "ADV_HITTEST",
            "IGNORE_LAYOUT",
            "FLOATING",
            "HIDDEN",
        ];
        let desired: BTreeSet<_> = s(&n.props, "widgetFlags").split('|').collect();
        for flag in flags {
            let add = desired.contains(flag);
            writeln!(
                screens,
                "lv_obj_{}_flag({},LV_OBJ_FLAG_{});",
                if add { "add" } else { "remove" },
                n.id,
                flag
            )
            .unwrap();
        }
        for state in s(&n.props, "states").split('|').filter(|s| !s.is_empty()) {
            writeln!(screens, "lv_obj_add_state({},LV_STATE_{state});", n.id).unwrap();
        }
        for (key, constant) in [
            ("hiddenFlag", "LV_OBJ_FLAG_HIDDEN"),
            ("clickableFlag", "LV_OBJ_FLAG_CLICKABLE"),
        ] {
            if let Some(on) = n.props[key].as_bool() {
                writeln!(
                    screens,
                    "lv_obj_{}_flag({},{constant});",
                    if on { "add" } else { "remove" },
                    n.id
                )
                .unwrap();
            }
        }
        for (key, constant) in [
            ("checkedState", "LV_STATE_CHECKED"),
            ("disabledState", "LV_STATE_DISABLED"),
        ] {
            if let Some(on) = n.props[key].as_bool() {
                writeln!(
                    screens,
                    "lv_obj_{}_state({},{constant});",
                    if on { "add" } else { "remove" },
                    n.id
                )
                .unwrap();
            }
        }
        let mut stylebody = String::new();
        for (part, states) in n.props["localStyles"]["definition"]
            .as_object()
            .into_iter()
            .flatten()
        {
            for (state, props) in states.as_object().into_iter().flatten() {
                let selector = format!(
                    "LV_PART_{part} | {}",
                    state
                        .split('|')
                        .map(|s| format!("LV_STATE_{s}"))
                        .collect::<Vec<_>>()
                        .join(" | ")
                );
                for (key, value) in props.as_object().into_iter().flatten() {
                    writeln!(
                        stylebody,
                        "lv_obj_set_style_{key}(obj, {} as _, {selector});",
                        style_value(key, value, &n.path)?
                    )
                    .unwrap();
                }
            }
        }
        let fontargs = p
            .fonts
            .iter()
            .map(|f| format!("font_{}", ident(s(f, "name"))))
            .collect::<Vec<_>>();
        writeln!(styles,"#[allow(unsafe_op_in_unsafe_fn,unused_variables)]\npub(super) unsafe fn style_{}(obj:*mut lv_obj_t {}) {{\n{stylebody}}}",n.id,fontargs.iter().map(|a|format!(",{a}:*mut lv_font_t")).collect::<String>()).unwrap();
        writeln!(
            screens,
            "super::styles::style_{}({}{});",
            n.id,
            n.id,
            fontargs.iter().map(|a| format!(",{a}")).collect::<String>()
        )
        .unwrap();
        if n.kind == "LVGLLabelWidget" {
            writeln!(
                screens,
                "reez_lvgl::text({}, {});lv_label_set_long_mode({},LV_LABEL_LONG_MODE_{});",
                n.id,
                rs_string(s(&n.props, "text")),
                n.id,
                if s(&n.props, "longMode").is_empty() {
                    "WRAP"
                } else {
                    s(&n.props, "longMode")
                }
            )
            .unwrap();
        }
    }
    writeln!(
        screens,
        "Self {{ {}, fonts, _thread:PhantomData }}\n}}",
        p.nodes
            .iter()
            .map(|n| n.id.clone())
            .collect::<Vec<_>>()
            .join(",")
    )
    .unwrap();
    screens.push_str("/// # Safety\n/// Call only on the owning LVGL thread.\npub unsafe fn load_screen(&self,id:usize) { unsafe { let obj=match id {\n");
    for (i, (_, id)) in p.pages.iter().enumerate() {
        writeln!(screens, "{}=>self.{id},", i + 1).unwrap();
    }
    screens.push_str("_=>panic!(\"invalid screen ID\")};lv_screen_load_anim(obj,LV_SCREEN_LOAD_ANIM_FADE_IN,200,0,false);}}\n");
    screens.push_str("pub fn object(&self,name:&str)->Option<*mut lv_obj_t>{match name {\n");
    for n in &p.nodes {
        if !s(&n.props, "identifier").is_empty() {
            writeln!(
                screens,
                "{}=>Some(self.{}),",
                rs_string(s(&n.props, "identifier")),
                n.id
            )
            .unwrap();
        }
    }
    screens.push_str("_=>None}}\npub fn font(&self,index:usize)->Option<*mut lv_font_t>{self.fonts.get(index).copied()}\n}\nimpl Drop for Ui {fn drop(&mut self){unsafe {\n// Switch away before deleting any owned screen.\nlet display=lv_display_get_default();if !display.is_null(){let blank=lv_obj_create(null_mut());lv_screen_load(blank);}\n");
    for (_, id) in &p.pages {
        writeln!(screens, "lv_obj_delete(self.{id});").unwrap();
    }
    screens.push_str("for font in self.fonts.drain(..){lv_binfont_destroy(font);}\n}}}\n");
    let root = "// Generated by reez. Requires reez-lvgl with matching LVGL configuration.\nextern crate alloc;\npub mod resources;\npub mod styles;\npub mod screens;\npub use screens::Ui;\n";
    Ok(BTreeMap::from([
        ("mod.rs".into(), root.into()),
        ("screens.rs".into(), screens),
        ("styles.rs".into(), styles),
        ("resources.rs".into(), resources),
    ]))
}
#[derive(Serialize, Deserialize)]
struct Manifest {
    schema: u32,
    files: Vec<String>,
}
/// Commit a complete output directory, retaining user-owned files and rolling back on rename failure.
pub fn publish(output: &Path, files: &BTreeMap<String, String>) -> Result<()> {
    let parent = output
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent).map_err(io)?;
    if output.is_symlink() {
        return err("output", "symlink output directory is not supported");
    }
    let lock = parent.join(format!(
        ".{}.reez-lock",
        output.file_name().unwrap().to_string_lossy()
    ));
    let _lock = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&lock)
        .map_err(|e| Diagnostic {
            path: lock.display().to_string(),
            message: format!("concurrent build or stale lock: {e}"),
        })?;
    struct Unlock(PathBuf);
    impl Drop for Unlock {
        fn drop(&mut self) {
            let _ = fs::remove_file(&self.0);
        }
    }
    let _unlock = Unlock(lock);
    let old = output.join(".reez-manifest.json");
    let previous: Manifest = if old.exists() {
        serde_json::from_slice(&fs::read(&old).map_err(io)?).map_err(io)?
    } else {
        Manifest {
            schema: 1,
            files: vec![],
        }
    };
    for n in previous.files.iter().chain(files.keys()) {
        if Path::new(n).components().count() != 1 || n.starts_with('.') || n.contains(['/', '\\']) {
            return err("manifest", "invalid generated filename");
        }
    }
    for n in files.keys() {
        if output.join(n).exists() && !previous.files.contains(n) {
            return err(n, "refusing to overwrite unowned file");
        }
    }
    let manifest = serde_json::to_string_pretty(&Manifest {
        schema: 1,
        files: files.keys().cloned().collect(),
    })
    .map_err(io)?;
    if previous.files == files.keys().cloned().collect::<Vec<_>>()
        && files
            .iter()
            .all(|(n, s)| fs::read(output.join(n)).ok().as_deref() == Some(s.as_bytes()))
    {
        return Ok(());
    }
    let temp = tempfile::tempdir_in(parent).map_err(io)?;
    let stage = temp.path().join("stage");
    fs::create_dir(&stage).map_err(io)?;
    fn copy(src: &Path, dst: &Path) -> Result<()> {
        for e in fs::read_dir(src).map_err(io)? {
            let e = e.map_err(io)?;
            let p = e.path();
            if p.is_symlink() {
                return err(p.display().to_string(), "output contains a symlink");
            }
            let d = dst.join(e.file_name());
            if p.is_dir() {
                fs::create_dir(&d).map_err(io)?;
                copy(&p, &d)?;
            } else {
                fs::copy(p, d).map_err(io)?;
            }
        }
        Ok(())
    }
    if output.exists() {
        copy(output, &stage)?;
    }
    for n in &previous.files {
        if stage.join(n).exists() {
            fs::remove_file(stage.join(n)).map_err(io)?;
        }
    }
    for (n, s) in files {
        fs::write(stage.join(n), s).map_err(io)?;
    }
    fs::write(stage.join(".reez-manifest.json"), manifest).map_err(io)?;
    let backup = temp.path().join("backup");
    let had = output.exists();
    if had {
        fs::rename(output, &backup).map_err(io)?;
    }
    if let Err(e) = fs::rename(&stage, output) {
        if had {
            fs::rename(backup, output).map_err(io)?;
        }
        return Err(io(e));
    }
    Ok(())
}
pub fn build(input: &Path, output: &Path, check: bool, options: &Options) -> Result<usize> {
    let source: Value = serde_json::from_slice(&fs::read(input).map_err(io)?).map_err(io)?;
    let p = parse(source)?;
    let base = input
        .parent()
        .unwrap_or(Path::new("."))
        .canonicalize()
        .map_err(io)?;
    let output = std::path::absolute(output).map_err(io)?;
    // Resolve existing ancestors so aliases and '..' cannot evade overlap checks.
    fn resolved(path: &Path) -> std::io::Result<PathBuf> {
        if path.exists() {
            return path.canonicalize();
        }
        let parent = path
            .parent()
            .ok_or_else(|| std::io::Error::other("invalid output path"))?;
        Ok(resolved(parent)?.join(
            path.file_name()
                .ok_or_else(|| std::io::Error::other("invalid output name"))?,
        ))
    }
    let output = resolved(&output).map_err(io)?;
    let c_out = resolved(
        &base.join(s(&p.source["settings"]["build"], "destinationFolder").replace('\\', "/")),
    )
    .map_err(io)?;
    if base.starts_with(&output) || output.starts_with(&c_out) || c_out.starts_with(&output) {
        return err(
            "output",
            "Rust output must be separate from project and C output directories",
        );
    }
    if !check {
        let files = generate(&p, input.parent().unwrap_or(Path::new(".")), options)?;
        publish(&output, &files)?;
    }
    Ok(p.nodes.len())
}
