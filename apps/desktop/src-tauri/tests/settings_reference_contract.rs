use serde_json::Value;

#[test]
fn settings_reference_is_a_separate_non_product_build_lane() {
    let config: Value =
        serde_json::from_str(include_str!("../tauri.settings-reference.conf.json")).unwrap();
    let windows = config.pointer("/app/windows").unwrap().as_array().unwrap();

    assert_eq!(
        config.get("identifier").and_then(Value::as_str),
        Some("com.ninochavez.local-meeting-notes.settings-reference")
    );
    assert_eq!(
        config
            .pointer("/build/frontendDist")
            .and_then(Value::as_str),
        Some("../settings-reference")
    );
    assert_eq!(windows.len(), 1);
    assert_eq!(
        windows[0].get("label").and_then(Value::as_str),
        Some("settings-reference-host")
    );
    assert_eq!(
        config
            .pointer("/app/security/capabilities/0")
            .and_then(Value::as_str),
        Some("settings-reference-window")
    );
    assert!(config.pointer("/bundle/resources").unwrap().is_null());
}

#[test]
fn native_plumbing_owns_menu_shortcut_bounds_focus_and_close() {
    let rust = include_str!("../src/settings_reference.rs");

    assert!(rust.contains("MenuItemBuilder::with_id(SETTINGS_MENU_ID, \"Settings…\")"));
    assert!(rust.contains(".accelerator(\"CmdOrCtrl+,\")"));
    assert!(rust.contains("WebviewUrl::App(\"settings.html\".into())"));
    assert!(rust.contains(".inner_size(720.0, 560.0)"));
    assert!(rust.contains(".min_inner_size(720.0, 560.0)"));
    assert!(rust.contains(".max_inner_size(720.0, 560.0)"));
    assert!(rust.contains(".resizable(false)"));
    assert!(rust.contains(".minimizable(false)"));
    assert!(rust.contains(".maximizable(false)"));
    assert!(rust.contains(".closable(true)"));
    assert!(rust.contains("window.set_focus()?"));
    assert!(!rust.contains("CloseRequested"));
}

#[test]
fn reference_capability_cannot_reach_product_commands_or_storage() {
    let capability: Value =
        serde_json::from_str(include_str!("../capabilities/settings-reference.json")).unwrap();
    let permissions = capability.get("permissions").unwrap().as_array().unwrap();

    assert_eq!(permissions.len(), 1);
    assert_eq!(permissions[0].as_str(), Some("core:window:allow-set-title"));
    assert_eq!(
        capability.pointer("/windows/0").and_then(Value::as_str),
        Some("settings-reference-host")
    );
    assert_eq!(
        capability.pointer("/windows/1").and_then(Value::as_str),
        Some("settings-reference")
    );
}

#[test]
fn product_ui_files_are_not_inputs_to_the_reference() {
    let config = include_str!("../tauri.settings-reference.conf.json");
    let rust = include_str!("../src/settings_reference.rs");

    for forbidden in ["../ui", "main.js", "styles.css", "native-calibration.css"] {
        assert!(!config.contains(forbidden));
        assert!(!rust.contains(forbidden));
    }
}
