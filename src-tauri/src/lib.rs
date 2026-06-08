// Tauri v2 desktop shell for the Klodik overlay.
// Prevents console window in release builds on Windows.

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                let icon_bytes = std::fs::read("src-tauri/icons/icon.png")
                    .or_else(|_| std::fs::read("icons/icon.png"))
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
