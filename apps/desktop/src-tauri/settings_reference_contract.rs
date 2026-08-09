use serde_json::Value;

use crate::build_contract::BuildPlan;

const IDENTIFIER: &str = "com.ninochavez.local-meeting-notes.settings-reference";
const FRONTEND: &str = "../settings-reference";
const HOST_WINDOW: &str = "settings-reference-host";
const CAPABILITY: &str = "settings-reference-window";

pub fn plan() -> BuildPlan {
    BuildPlan {
        commands: &[],
        capabilities_path: "capabilities/settings-reference.json",
        permissions_path: "permissions/settings-reference/**/*",
    }
}

pub fn validate(config: &Value) -> Result<(), &'static str> {
    let windows = config
        .pointer("/app/windows")
        .and_then(Value::as_array)
        .ok_or("the Settings reference must declare its host window")?;
    let capabilities = config
        .pointer("/app/security/capabilities")
        .and_then(Value::as_array)
        .ok_or("the Settings reference must declare its isolated capability")?;

    if config.get("productName").and_then(Value::as_str) != Some("Yawn Settings Reference")
        || config.get("identifier").and_then(Value::as_str) != Some(IDENTIFIER)
        || config
            .pointer("/build/frontendDist")
            .and_then(Value::as_str)
            != Some(FRONTEND)
        || config
            .pointer("/build/features")
            .and_then(Value::as_array)
            .is_none_or(|features| {
                features.len() != 1 || features[0].as_str() != Some("settings-reference")
            })
        || windows.len() != 1
        || windows[0].get("label").and_then(Value::as_str) != Some(HOST_WINDOW)
        || capabilities.len() != 1
        || capabilities[0].as_str() != Some(CAPABILITY)
        || config.pointer("/bundle/active").and_then(Value::as_bool) != Some(true)
        || !config
            .pointer("/bundle/resources")
            .is_none_or(Value::is_null)
    {
        return Err(
            "the Settings reference requires its isolated identifier, frontend, feature, sole host window/capability, and no product runtime resources",
        );
    }

    Ok(())
}
