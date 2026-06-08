// Tauri v2 desktop shell for the Klodik overlay.
// Prevents console window in release builds on Windows.

use tauri::Manager;
use tauri::path::BaseDirectory;

#[cfg(windows)]
mod win32 {
    use std::ffi::c_void;

    pub const GWL_EXSTYLE: i32 = -20;
    pub const WS_EX_TOOLWINDOW: i32 = 0x00000080;

    pub const DWMWA_BORDER_COLOR: u32 = 34;
    pub const DWMWA_COLOR_NONE: u32 = 0xFFFFFFFE;
    pub const DWMWA_WINDOW_CORNER_PREFERENCE: u32 = 33;
    pub const DWMWCP_DONOTROUND: u32 = 1;

    extern "system" {
        pub fn GetWindowLongPtrW(hwnd: *mut c_void, nIndex: i32) -> isize;
        pub fn SetWindowLongPtrW(hwnd: *mut c_void, nIndex: i32, dwNewLong: isize) -> isize;
        pub fn SetWindowPos(
            hwnd: *mut c_void,
            hwndInsertAfter: *mut c_void,
            x: i32, y: i32, cx: i32, cy: i32,
            uFlags: u32,
        ) -> i32;
        pub fn DwmSetWindowAttribute(
            hwnd: *mut c_void,
            dwAttribute: u32,
            pvAttribute: *const c_void,
            cbAttribute: u32,
        ) -> i32;
    }

    pub const SWP_FRAMECHANGED: u32 = 0x0020;
    pub const SWP_NOMOVE: u32 = 0x0002;
    pub const SWP_NOSIZE: u32 = 0x0001;
    pub const SWP_NOZORDER: u32 = 0x0004;
    pub const SWP_NOACTIVATE: u32 = 0x0010;
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                #[cfg(windows)]
                {
                    if let Ok(hwnd) = window.hwnd() {
                        let hwnd_ptr = hwnd.0 as *mut std::ffi::c_void;
                        unsafe {
                            // 1) Add WS_EX_TOOLWINDOW — убирает тень и таскбар
                            let exstyle = win32::GetWindowLongPtrW(hwnd_ptr, win32::GWL_EXSTYLE);
                            win32::SetWindowLongPtrW(
                                hwnd_ptr,
                                win32::GWL_EXSTYLE,
                                exstyle | win32::WS_EX_TOOLWINDOW as isize,
                            );

                            // 2) Remove DWM accent border (Windows 11)
                            let border_color = win32::DWMWA_COLOR_NONE;
                            let _ = win32::DwmSetWindowAttribute(
                                hwnd_ptr,
                                win32::DWMWA_BORDER_COLOR,
                                &border_color as *const _ as *const _,
                                std::mem::size_of::<u32>() as u32,
                            );

                            // 3) Disable rounded corners (Windows 11)
                            let corner = win32::DWMWCP_DONOTROUND;
                            let _ = win32::DwmSetWindowAttribute(
                                hwnd_ptr,
                                win32::DWMWA_WINDOW_CORNER_PREFERENCE,
                                &corner as *const _ as *const _,
                                std::mem::size_of::<u32>() as u32,
                            );

                            // 4) Force frame recalculation — last, after all DWM changes
                            win32::SetWindowPos(
                                hwnd_ptr,
                                std::ptr::null_mut(),
                                0, 0, 0, 0,
                                win32::SWP_FRAMECHANGED
                                    | win32::SWP_NOMOVE
                                    | win32::SWP_NOSIZE
                                    | win32::SWP_NOZORDER
                                    | win32::SWP_NOACTIVATE,
                            );
                        }
                    }
                }

                let icon_bytes = app.path()
                    .resolve("icons/icon.png", BaseDirectory::Resource)
                    .and_then(|p| Ok(std::fs::read(&p).unwrap_or_default()))
                    .unwrap_or_default();
                if !icon_bytes.is_empty() {
                    if let Ok(img) = image::load_from_memory(&icon_bytes) {
                        let rgba = img.to_rgba8();
                        let (width, height) = rgba.dimensions();
                        let icon = tauri::image::Image::new_owned(rgba.into_raw(), width, height);
                        let _ = window.set_icon(icon);
                    }
                }
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
