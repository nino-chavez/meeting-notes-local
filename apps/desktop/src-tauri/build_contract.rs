use serde_json::Value;

pub const DEV_IDENTIFIER: &str = "com.ninochavez.local-meeting-notes.library-dev";
pub const DEV_WINDOW: &str = "library-dev";
pub const DEV_CAPABILITY: &str = "library-dev-window";
pub const DEV_FRONTEND: &str = "../library-dev-ui";
pub const PREVIEW_IDENTIFIER: &str = "com.ninochavez.local-meeting-notes.preview";
pub const PREVIEW_WINDOW: &str = "preview";
pub const PREVIEW_CAPABILITY: &str = "preview-window";
pub const PREVIEW_FRONTEND: &str = "../ui";
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

const PREVIEW_COMMANDS: &[&str] = &[
    "app_snapshot",
    "start_meeting",
    "stop_meeting",
    "dismiss_meeting",
    "retry_startup",
    "preview_library_snapshot",
    "preview_library_search",
    "preview_library_open_search_result",
    "preview_library_open_note",
    "preview_library_open_evidence",
    "preview_library_open_transcript",
];

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum BuildMode {
    Production,
    Development,
    Preview,
}

pub struct BuildPlan {
    pub commands: &'static [&'static str],
    pub capabilities_path: &'static str,
    pub permissions_path: &'static str,
}

impl BuildMode {
    pub fn from_enabled_features(
        library_development: bool,
        preview: bool,
    ) -> Result<Self, &'static str> {
        match (library_development, preview) {
            (false, false) => Ok(Self::Production),
            (true, false) => Ok(Self::Development),
            (false, true) => Ok(Self::Preview),
            (true, true) => Err("library development and preview are isolated build lanes"),
        }
    }
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
        BuildMode::Preview => BuildPlan {
            commands: PREVIEW_COMMANDS,
            capabilities_path: "capabilities/preview.json",
            permissions_path: "permissions/production/**/*",
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
        BuildMode::Preview if is_preview_config(config) => Ok(()),
        BuildMode::Preview => Err(
            "preview-surface requires tauri.preview.conf.json with its isolated identifier, product frontend, sole window/capability, ad-hoc signing, and the complete runtime resource contract",
        ),
    }
}

fn is_preview_config(config: &Value) -> bool {
    config.get("productName").and_then(Value::as_str) == Some("Local Meeting Notes Preview")
        && config.get("identifier").and_then(Value::as_str) == Some(PREVIEW_IDENTIFIER)
        && config
            .pointer("/build/frontendDist")
            .and_then(Value::as_str)
            == Some(PREVIEW_FRONTEND)
        && has_single_window(
            config.pointer("/app/windows"),
            PREVIEW_WINDOW,
            "Local Meeting Notes — Preview",
        )
        && has_single_string(
            config.pointer("/app/security/capabilities"),
            PREVIEW_CAPABILITY,
        )
        && config.pointer("/bundle/active").and_then(Value::as_bool) == Some(true)
        && config.pointer("/bundle/resources") == Some(&production_resources())
        && config
            .pointer("/bundle/macOS/minimumSystemVersion")
            .and_then(Value::as_str)
            == Some("14.4")
        && config
            .pointer("/bundle/macOS/signingIdentity")
            .and_then(Value::as_str)
            == Some("-")
}

fn is_production_config(config: &Value) -> bool {
    config.get("productName").and_then(Value::as_str) == Some("Local Meeting Notes")
        && config.get("identifier").and_then(Value::as_str) == Some(PRODUCTION_IDENTIFIER)
        && config
            .pointer("/build/frontendDist")
            .and_then(Value::as_str)
            == Some(PRODUCTION_FRONTEND)
        && has_single_window(
            config.pointer("/app/windows"),
            PRODUCTION_WINDOW,
            "Local Meeting Notes",
        )
        && has_single_string(
            config.pointer("/app/security/capabilities"),
            PRODUCTION_CAPABILITY,
        )
        && config.pointer("/bundle/active").and_then(Value::as_bool) == Some(true)
        && config.pointer("/bundle/resources") == Some(&production_resources())
}

fn is_development_config(config: &Value) -> bool {
    config.get("productName").and_then(Value::as_str)
        == Some("Local Meeting Notes Library Development Surface")
        && config.get("identifier").and_then(Value::as_str) == Some(DEV_IDENTIFIER)
        && config
            .pointer("/build/frontendDist")
            .and_then(Value::as_str)
            == Some(DEV_FRONTEND)
        && has_single_window(
            config.pointer("/app/windows"),
            DEV_WINDOW,
            "Local Meeting Notes — Library Development Surface",
        )
        && has_single_string(config.pointer("/app/security/capabilities"), DEV_CAPABILITY)
        && config.pointer("/bundle/active").and_then(Value::as_bool) == Some(false)
        && config
            .pointer("/bundle/resources")
            .is_some_and(Value::is_null)
}

fn has_single_window(value: Option<&Value>, expected_label: &str, expected_title: &str) -> bool {
    value.and_then(Value::as_array).is_some_and(|windows| {
        windows.len() == 1
            && windows[0].get("label").and_then(Value::as_str) == Some(expected_label)
            && windows[0].get("title").and_then(Value::as_str) == Some(expected_title)
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
        "../runtime/note-bridge.py": "note-bridge.py",
        "../runtime/note-runtime-project.json": "note-runtime-project.json",
        "../runtime/note-validator.zip": "note-validator.zip",
        "../runtime/notes": "notes",
        "../runtime/python-runtime": "python-runtime",
        "../runtime/spike": "spike",
        "../runtime/worker": "worker",
    })
}
