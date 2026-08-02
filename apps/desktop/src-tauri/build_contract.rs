use serde_json::Value;

pub const DEV_IDENTIFIER: &str = "com.ninochavez.local-meeting-notes.library-dev";
pub const DEV_WINDOW: &str = "library-dev";
pub const DEV_CAPABILITY: &str = "library-dev-window";
pub const DEV_FRONTEND: &str = "../library-dev-ui";

const PRODUCTION_COMMANDS: &[&str] = &[
    "app_snapshot",
    "start_meeting",
    "stop_meeting",
    "dismiss_meeting",
    "retry_startup",
];

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum BuildMode {
    Production,
    Development,
}

pub struct BuildPlan {
    pub commands: &'static [&'static str],
    pub capabilities_path: &'static str,
    pub permissions_path: &'static str,
}

pub fn plan(mode: BuildMode) -> BuildPlan {
    match mode {
        BuildMode::Production => BuildPlan {
            commands: PRODUCTION_COMMANDS,
            capabilities_path: "capabilities/main.json",
            permissions_path: "permissions/production/**/*",
        },
        BuildMode::Development => BuildPlan {
            commands: &[],
            capabilities_path: "capabilities/development/library-dev.json",
            permissions_path: "permissions/development/**/*",
        },
    }
}

pub fn validate(mode: BuildMode, config: &Value) -> Result<(), &'static str> {
    let identifier = config.get("identifier").and_then(Value::as_str);
    let frontend = config
        .pointer("/build/frontendDist")
        .and_then(Value::as_str);
    let window = config
        .pointer("/app/windows/0/label")
        .and_then(Value::as_str);
    let capabilities = config
        .pointer("/app/security/capabilities")
        .and_then(Value::as_array);
    let bundle_active = config.pointer("/bundle/active").and_then(Value::as_bool);
    let resources = config.pointer("/bundle/resources");
    let is_development_config = identifier == Some(DEV_IDENTIFIER)
        && frontend == Some(DEV_FRONTEND)
        && window == Some(DEV_WINDOW)
        && capabilities.is_some_and(|entries| {
            entries.len() == 1 && entries[0].as_str() == Some(DEV_CAPABILITY)
        })
        && bundle_active == Some(false)
        && resources.is_some_and(Value::is_null);

    match mode {
        BuildMode::Development if is_development_config => Ok(()),
        BuildMode::Development => Err(
            "library-dev-surface requires tauri.library-dev.conf.json with the isolated identifier, frontend, window, capability, and no-bundle resources",
        ),
        BuildMode::Production if !is_development_config => Ok(()),
        BuildMode::Production => Err(
            "the library development Tauri configuration requires the library-dev-surface feature",
        ),
    }
}
