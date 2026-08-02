use serde_json::Value;

pub const DEV_IDENTIFIER: &str = "com.ninochavez.local-meeting-notes.library-dev";
pub const DEV_WINDOW: &str = "library-dev";
pub const DEV_CAPABILITY: &str = "library-dev-window";
pub const DEV_FRONTEND: &str = "../library-dev-ui";
pub const PRODUCTION_IDENTIFIER: &str = "com.ninochavez.local-meeting-notes";
pub const PRODUCTION_WINDOW: &str = "main";
pub const PRODUCTION_CAPABILITY: &str = "main-window";
pub const PRODUCTION_FRONTEND: &str = "../ui";

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
    match mode {
        BuildMode::Production if is_production_config(config) => Ok(()),
        BuildMode::Production => Err(
            "the bundled shell requires the frozen production identifier, frontend, sole main window/capability, and runtime resource contract",
        ),
        BuildMode::Development if is_development_config(config) => Ok(()),
        BuildMode::Development => Err(
            "library-dev-surface requires tauri.library-dev.conf.json with the isolated identifier, frontend, sole window/capability, and no-bundle resources",
        ),
    }
}

fn is_production_config(config: &Value) -> bool {
    config.get("identifier").and_then(Value::as_str) == Some(PRODUCTION_IDENTIFIER)
        && config
            .pointer("/build/frontendDist")
            .and_then(Value::as_str)
            == Some(PRODUCTION_FRONTEND)
        && has_single_label(config.pointer("/app/windows"), PRODUCTION_WINDOW)
        && has_single_string(
            config.pointer("/app/security/capabilities"),
            PRODUCTION_CAPABILITY,
        )
        && config.pointer("/bundle/active").and_then(Value::as_bool) == Some(true)
        && config.pointer("/bundle/resources") == Some(&production_resources())
}

fn is_development_config(config: &Value) -> bool {
    config.get("identifier").and_then(Value::as_str) == Some(DEV_IDENTIFIER)
        && config
            .pointer("/build/frontendDist")
            .and_then(Value::as_str)
            == Some(DEV_FRONTEND)
        && has_single_label(config.pointer("/app/windows"), DEV_WINDOW)
        && has_single_string(config.pointer("/app/security/capabilities"), DEV_CAPABILITY)
        && config.pointer("/bundle/active").and_then(Value::as_bool) == Some(false)
        && config
            .pointer("/bundle/resources")
            .is_some_and(Value::is_null)
}

fn has_single_label(value: Option<&Value>, expected: &str) -> bool {
    value.and_then(Value::as_array).is_some_and(|windows| {
        windows.len() == 1 && windows[0].get("label").and_then(Value::as_str) == Some(expected)
    })
}

fn has_single_string(value: Option<&Value>, expected: &str) -> bool {
    value
        .and_then(Value::as_array)
        .is_some_and(|entries| entries.len() == 1 && entries[0].as_str() == Some(expected))
}

fn production_resources() -> Value {
    serde_json::json!({
        "../runtime/app-runtime.json": "app-runtime.json",
        "../runtime/bin": "bin",
        "../runtime/encoder-unavailable.identity": "encoder-unavailable.identity",
        "../runtime/models": "models",
        "../runtime/notes": "notes",
        "../runtime/python-runtime": "python-runtime",
        "../runtime/spike": "spike",
        "../runtime/worker": "worker",
    })
}
