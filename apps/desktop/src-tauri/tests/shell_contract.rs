use serde_json::Value;

#[test]
fn single_instance_is_the_first_plugin_and_precedes_app_setup() {
    let source = include_str!("../src/main.rs");
    let plugin = source
        .find(".plugin(tauri_plugin_single_instance::init")
        .expect("single-instance plugin registration");
    let setup = source.find(".setup(|app|").expect("startup setup hook");

    assert_eq!(source.find(".plugin("), Some(plugin));
    assert!(plugin < setup);
}

#[test]
fn main_window_has_only_named_commands_and_no_generic_capability() {
    let capability: Value =
        serde_json::from_str(include_str!("../capabilities/main.json")).unwrap();
    assert_eq!(capability["windows"], serde_json::json!(["main"]));
    assert_eq!(
        capability["permissions"],
        serde_json::json!([
            "allow-app-snapshot",
            "allow-start-meeting",
            "allow-stop-meeting",
            "allow-dismiss-meeting",
            "allow-retry-startup"
        ])
    );
    assert!(capability.get("remote").is_none());
    let serialized = serde_json::to_string(&capability).unwrap();
    for forbidden in ["shell:", "fs:", "process:", "dialog:", "http:"] {
        assert!(
            !serialized.contains(forbidden),
            "forbidden capability {forbidden}"
        );
    }
}

#[test]
fn product_operation_facade_remains_unregistered() {
    let source = include_str!("../src/main.rs");
    let handler_start = source
        .find(".invoke_handler(tauri::generate_handler![")
        .expect("named command handler");
    let handler_end = source[handler_start..]
        .find("])")
        .expect("named command handler end")
        + handler_start;
    let handler = &source[handler_start..handler_end];

    assert!(source.contains("mod product_facade;"));
    assert!(!handler.contains("restore_withheld_turn"));
    assert!(!handler.contains("regenerate_note"));
}

#[test]
fn bundled_shell_uses_restrictive_local_csp() {
    let config: Value = serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
    let security = &config["app"]["security"];
    assert_eq!(security["capabilities"], serde_json::json!(["main-window"]));
    assert_eq!(security["freezePrototype"], true);
    let csp = security["csp"].as_str().unwrap();
    assert!(csp.contains("default-src 'self'"));
    assert!(csp.contains("object-src 'none'"));
    assert!(csp.contains("form-action 'none'"));
    assert!(!csp.contains("https:"));
    assert!(!csp.contains("*"));
}

#[test]
fn shell_renders_safe_state_before_runtime_preflight() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");
    assert!(html.contains("data-startup-state=\"shell-rendered\""));
    assert!(html.contains("Nothing is recording"));
    assert!(html.contains("The window opens before any audio or model process starts."));
    for command in [
        "app_snapshot",
        "start_meeting",
        "stop_meeting",
        "dismiss_meeting",
        "retry_startup",
    ] {
        assert!(script.contains(&format!("invoke(\"{command}\"")));
    }
    assert!(!script.contains("innerHTML"));
    assert!(!script.contains("Internal beta"));
    assert!(!script.contains("Command.sidecar"));
    assert!(!script.contains("window.__TAURI__.fs"));
}

#[test]
fn macos_bundle_declares_capture_purposes_and_common_resources() {
    let plist = include_str!("../Info.plist");
    assert!(plist.contains("NSMicrophoneUsageDescription"));
    assert!(plist.contains("NSAudioCaptureUsageDescription"));
    assert!(plist.contains("meetings you start"));
    assert!(plist.contains("local transcript"));
    assert!(!plist.contains("local notes"));

    let html = include_str!("../../ui/index.html");
    assert!(html.contains("deletion runs the next time it opens"));

    let config: Value = serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
    assert_eq!(config["bundle"]["macOS"]["minimumSystemVersion"], "14.4");
    assert_eq!(
        config["bundle"]["resources"]["../runtime/app-runtime.json"],
        "app-runtime.json"
    );
    assert_eq!(
        config["bundle"]["icon"],
        serde_json::json!(["icons/icon.png"])
    );

    let boundary: Value =
        serde_json::from_str(include_str!("../tauri.boundary.conf.json")).unwrap();
    assert_eq!(boundary["bundle"]["macOS"]["signingIdentity"], "-");
    assert!(boundary["bundle"].get("resources").is_none());
}
