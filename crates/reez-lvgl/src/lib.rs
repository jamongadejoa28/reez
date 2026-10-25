#![no_std]
//! Target-matched LVGL bindings and generated UI primitives.
extern crate alloc;
#[allow(
    non_camel_case_types,
    non_snake_case,
    non_upper_case_globals,
    unsafe_op_in_unsafe_fn,
    clippy::all,
    unnecessary_transmutes
)]
pub mod sys {
    include!(concat!(env!("OUT_DIR"), "/bindings.rs"));
}
use sys::*;
pub fn color(rgb: u32) -> lv_color_t {
    lv_color_t {
        blue: rgb as u8,
        green: (rgb >> 8) as u8,
        red: (rgb >> 16) as u8,
    }
}
/// LVGL percentage coordinate encoding (LVGL 9.5).
pub fn pct(value: i32) -> i32 {
    // Pure arithmetic in LVGL; no object, global state, or initialization required.
    unsafe { lv_pct(value) }
}
/// # Safety
/// `obj` must be a live label on the current LVGL thread.
pub unsafe fn text(obj: *mut lv_obj_t, value: &str) {
    let s = alloc::ffi::CString::new(value).expect("label contains NUL");
    unsafe {
        lv_label_set_text(obj, s.as_ptr());
    }
}
/// # Safety
/// `obj` must be live on the LVGL thread; `all` is a scalar style value.
pub unsafe fn pad(obj: *mut lv_obj_t, all: i32) {
    unsafe {
        lv_obj_set_style_pad_left(obj, all, 0);
        lv_obj_set_style_pad_right(obj, all, 0);
        lv_obj_set_style_pad_top(obj, all, 0);
        lv_obj_set_style_pad_bottom(obj, all, 0);
    }
}
