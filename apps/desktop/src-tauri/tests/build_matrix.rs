#[path = "../build_contract.rs"]
mod build_contract;

use build_contract::{BuildMode, plan, validate};
use serde_json::Value;

fn config(bytes: &str) -> Value {
    serde_json::from_str(bytes).unwrap()
}

#[test]
fn production_config_without_feature_is_production_only() {
    let production = config(include_str!("../tauri.conf.json"));
    let plan = plan(BuildMode::Production);
    assert!(validate(BuildMode::Production, &production).is_ok());
    assert_eq!(plan.capabilities_path, "capabilities/main.json");
    assert_eq!(plan.permissions_path, "permissions/production/**/*");
    assert_eq!(
        plan.commands,
        [
            "app_snapshot",
            "start_meeting",
            "stop_meeting",
            "dismiss_meeting",
            "retry_startup",
        ]
    );
}

#[test]
fn isolated_development_config_with_feature_is_development_only() {
    let development = config(include_str!("../tauri.library-dev.conf.json"));
    let plan = plan(BuildMode::Development);
    assert!(validate(BuildMode::Development, &development).is_ok());
    assert!(plan.commands.is_empty());
    assert_eq!(
        plan.capabilities_path,
        "capabilities/development/library-dev.json"
    );
    assert_eq!(plan.permissions_path, "permissions/development/**/*");
}

#[test]
fn feature_with_missing_or_production_configuration_fails_closed() {
    let production = config(include_str!("../tauri.conf.json"));
    let mut missing = production.clone();
    missing["identifier"] = Value::String(build_contract::DEV_IDENTIFIER.into());
    assert!(validate(BuildMode::Development, &production).is_err());
    assert!(validate(BuildMode::Development, &missing).is_err());
    assert!(
        validate(
            BuildMode::Production,
            &config(include_str!("../tauri.library-dev.conf.json"))
        )
        .is_err()
    );
}
