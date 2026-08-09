use tauri::{
    AppHandle, Manager, WebviewUrl, WebviewWindow,
    menu::{MenuBuilder, MenuItemBuilder, SubmenuBuilder},
    webview::WebviewWindowBuilder,
};

const SETTINGS_MENU_ID: &str = "open-settings-reference";
const SETTINGS_WINDOW_LABEL: &str = "settings-reference";

fn open_settings_window(app: &AppHandle) -> tauri::Result<WebviewWindow> {
    if let Some(window) = app.get_webview_window(SETTINGS_WINDOW_LABEL) {
        window.show()?;
        window.unminimize()?;
        window.set_focus()?;
        return Ok(window);
    }

    WebviewWindowBuilder::new(
        app,
        SETTINGS_WINDOW_LABEL,
        WebviewUrl::App("settings.html".into()),
    )
    .title("Capture — Yawn Settings")
    .inner_size(720.0, 560.0)
    .min_inner_size(720.0, 560.0)
    .max_inner_size(720.0, 560.0)
    .resizable(false)
    .minimizable(false)
    .maximizable(false)
    .closable(true)
    .center()
    .focused(true)
    .build()
}

pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let settings = MenuItemBuilder::with_id(SETTINGS_MENU_ID, "Settings…")
                .accelerator("CmdOrCtrl+,")
                .build(app)?;
            let app_menu = SubmenuBuilder::new(app, "Yawn Settings Reference")
                .about(None)
                .separator()
                .item(&settings)
                .separator()
                .hide()
                .hide_others()
                .show_all()
                .separator()
                .quit()
                .build()?;
            let menu = MenuBuilder::new(app).item(&app_menu).build()?;
            app.set_menu(menu)?;
            app.on_menu_event(|app, event| {
                if event.id() == SETTINGS_MENU_ID {
                    let _ = open_settings_window(app);
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Yawn Settings reference failed");
}
