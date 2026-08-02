#[path = "../build_contract.rs"]
mod build_contract;

use build_contract::{BuildMode, plan, validate};
use serde_json::{Value, json};

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
fn production_rejects_every_development_or_hybrid_field() {
    let production = config(include_str!("../tauri.conf.json"));
    let mut hybrids = Vec::new();

    let mut identifier = production.clone();
    identifier["identifier"] = Value::String(build_contract::DEV_IDENTIFIER.into());
    hybrids.push(identifier);

    let mut frontend = production.clone();
    frontend["build"]["frontendDist"] = Value::String(build_contract::DEV_FRONTEND.into());
    hybrids.push(frontend);

    let mut window = production.clone();
    window["app"]["windows"][0]["label"] = Value::String(build_contract::DEV_WINDOW.into());
    hybrids.push(window);

    let mut extra_window = production.clone();
    extra_window["app"]["windows"]
        .as_array_mut()
        .unwrap()
        .push(json!({
            "label": build_contract::DEV_WINDOW,
        }));
    hybrids.push(extra_window);

    let mut capability = production.clone();
    capability["app"]["security"]["capabilities"] = json!([build_contract::DEV_CAPABILITY]);
    hybrids.push(capability);

    let mut extra_capability = production.clone();
    extra_capability["app"]["security"]["capabilities"]
        .as_array_mut()
        .unwrap()
        .push(Value::String(build_contract::DEV_CAPABILITY.into()));
    hybrids.push(extra_capability);

    let mut inactive_bundle = production.clone();
    inactive_bundle["bundle"]["active"] = Value::Bool(false);
    hybrids.push(inactive_bundle);

    let mut empty_resources = production.clone();
    empty_resources["bundle"]["resources"] = Value::Null;
    hybrids.push(empty_resources);

    for hybrid in hybrids {
        assert!(validate(BuildMode::Production, &hybrid).is_err());
    }
}

#[test]
fn development_rejects_every_production_or_hybrid_field() {
    let development = config(include_str!("../tauri.library-dev.conf.json"));
    let production = config(include_str!("../tauri.conf.json"));
    let mut hybrids = Vec::new();

    let mut identifier = development.clone();
    identifier["identifier"] = Value::String(build_contract::PRODUCTION_IDENTIFIER.into());
    hybrids.push(identifier);

    let mut frontend = development.clone();
    frontend["build"]["frontendDist"] = Value::String(build_contract::PRODUCTION_FRONTEND.into());
    hybrids.push(frontend);

    let mut window = development.clone();
    window["app"]["windows"][0]["label"] = Value::String(build_contract::PRODUCTION_WINDOW.into());
    hybrids.push(window);

    let mut extra_window = development.clone();
    extra_window["app"]["windows"]
        .as_array_mut()
        .unwrap()
        .push(json!({
            "label": build_contract::PRODUCTION_WINDOW,
        }));
    hybrids.push(extra_window);

    let mut capability = development.clone();
    capability["app"]["security"]["capabilities"] = json!([build_contract::PRODUCTION_CAPABILITY]);
    hybrids.push(capability);

    let mut extra_capability = development.clone();
    extra_capability["app"]["security"]["capabilities"]
        .as_array_mut()
        .unwrap()
        .push(Value::String(build_contract::PRODUCTION_CAPABILITY.into()));
    hybrids.push(extra_capability);

    let mut active_bundle = development.clone();
    active_bundle["bundle"]["active"] = Value::Bool(true);
    hybrids.push(active_bundle);

    let mut production_resources = development.clone();
    production_resources["bundle"]["resources"] = production["bundle"]["resources"].clone();
    hybrids.push(production_resources);

    for hybrid in hybrids {
        assert!(validate(BuildMode::Development, &hybrid).is_err());
    }
}
