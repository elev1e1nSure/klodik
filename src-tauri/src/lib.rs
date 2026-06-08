// Tauri v2 desktop shell for the Klodik overlay.
// Prevents console window in release builds on Windows.

use tauri::Manager;
use tauri::path::BaseDirectory;

#[cfg(windows)]
mod win32 {
    use std::ffi::c_void;

    pub const GWL_STYLE: i32 = -16;
    pub const GWL_EXSTYLE: i32 = -20;

    pub const WS_POPUP: i32 = -0x80000000i32; // 0x80000000 as i32
    pub const WS_BORDER: i32 = 0x00800000;
    pub const WS_DLGFRAME: i32 = 0x00400000;
    pub const WS_THICKFRAME: i32 = 0x00040000;
    pub const WS_CAPTION: i32 = WS_DLGFRAME | WS_BORDER;
    pub const WS_CLIPCHILDREN: i32 = 0x02000000;
    pub const WS_CLIPSIBLINGS: i32 = 0x04000000;
    pub const WS_VISIBLE: i32 = 0x10000000;

    pub const WS_EX_TOOLWINDOW: i32 = 0x00000080;

    extern "system" {
        pub fn SetWindowLongPtrW(hwnd: *mut c_void, nIndex: i32, dwNewLong: isize) -> isize;
        pub fn GetWindowLongPtrW(hwnd: *mut c_void, nIndex: i32) -> isize;
        pub fn SetWindowPos(
            hwnd: *mut c_void,
            hwndInsertAfter: *mut c_void,
            x: i32, y: i32, cx: i32, cy: i32,
            uFlags: u32,
        ) -> i32;
    }

    pub const SWP_FRAMECHANGED: u32 = 0x0020;
    pub const SWP_NOMOVE: u32 = 0x0002;
    pub const SWP_NOSIZE: u32 = 0x0001;
    pub const SWP_NOZORDER: u32 = 0x0004;
    pub const SWP_NOACTIVATE: u32 = 0x0010;
    pub const SWP_SHOWWINDOW: u32 = 0x0040;
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                // Remove shadow/border on Windows: force WS_POPUP + WS_EX_TOOLWINDOW
                #[cfg(windows)]
                {
                    if let Ok(hwnd) = window.hwnd() {
                        let hwnd_ptr = hwnd.0 as *mut std::ffi::c_void;
                        unsafe {
                            // 1) Strip all frame styles from GWL_STYLE, keep only popup + visible + clip
                            let style = win32::GetWindowLongPtrW(hwnd_ptr, win32::GWL_STYLE);
                            let new_style = (style
                                & !(win32::WS_BORDER
                                    | win32::WS_DLGFRAME
                                    | win32::WS_THICKFRAME
                                    | win32::WS_CAPTION) as isize)
                                | (win32::WS_POPUP | win32::WS_VISIBLE | win32::WS_CLIPCHILDREN | win32::WS_CLIPSIBLINGS) as isize;
                            win32::SetWindowLongPtrW(hwnd_ptr, win32::GWL_STYLE, new_style);

                            // 2) Add WS_EX_TOOLWINDOW to extended style
                            let exstyle = win32::GetWindowLongPtrW(hwnd_ptr, win32::GWL_EXSTYLE);
                            win32::SetWindowLongPtrW(
                                hwnd_ptr,
                                win32::GWL_EXSTYLE,
                                exstyle | win32::WS_EX_TOOLWINDOW as isize,
                            );

                            // 3) Force frame recalculation
                            win32::SetWindowPos(
                                hwnd_ptr,
                                std::ptr::null_mut(),
                                0, 0, 0, 0,
                                win32::SWP_FRAMECHANGED
                                    | win32::SWP_NOMOVE
                                    | win32::SWP_NOSIZE
                                    | win32::SWP_NOZORDER
                                    | win32::SWP_NOACTIVATE
                                    | win32::SWP_SHOWWINDOW,
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
