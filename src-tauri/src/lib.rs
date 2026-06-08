// Tauri v2 desktop shell for the Klodik overlay.
// Prevents console window in release builds on Windows.

use tauri::Manager;
use tauri::path::BaseDirectory;

#[cfg(windows)]
mod dwm {
    use std::ffi::c_void;

    #[allow(non_snake_case)]
    extern "system" {
        pub fn DwmSetWindowAttribute(
            hwnd: *mut c_void,
            dwAttribute: u32,
            pvAttribute: *const c_void,
            cbAttribute: u32,
        ) -> i32;
    }

    pub const DWMWA_NCRENDERING_POLICY: u32 = 2;
    pub const DWMNCRP_DISABLED: u32 = 2;
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                // Remove DWM shadow on Windows for a clean overlay look
                #[cfg(windows)]
                {
                    if let Ok(hwnd) = window.hwnd() {
                        let policy = dwm::DWMNCRP_DISABLED;
                        let hwnd_ptr = hwnd.0 as *mut std::ffi::c_void;
                        unsafe {
                            let _ = dwm::DwmSetWindowAttribute(
                                hwnd_ptr,
                                dwm::DWMWA_NCRENDERING_POLICY,
                                &policy as *const _ as *const _,
                                std::mem::size_of::<u32>() as u32,
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
