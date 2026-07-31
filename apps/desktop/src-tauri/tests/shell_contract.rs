use serde_json::Value;

#[test]
fn main_window_has_one_named_command_and_no_generic_capability() {
    let capability: Value =
        serde_json::from_str(include_str!("../capabilities/main.json")).unwrap();
    assert_eq!(capability["windows"], serde_json::json!(["main"]));
    assert_eq!(
        capability["permissions"],
        serde_json::json!(["allow-startup-status"])
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
    assert!(html.contains("Nothing is recording."));
    assert!(html.contains("<button type=\"button\" disabled>"));
    assert!(html.contains("No microphone or system-audio process has started."));
    assert!(script.contains("invoke(\"startup_status\")"));
    assert!(!script.contains("Command.sidecar"));
    assert!(!script.contains("window.__TAURI__.fs"));
}
