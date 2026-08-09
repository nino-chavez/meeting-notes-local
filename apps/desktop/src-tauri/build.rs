mod build_contract;
mod settings_reference_contract;

use std::{env, fs};

use build_contract::{BuildMode, merge_config, plan, validate};

fn main() {
    println!("cargo:rerun-if-env-changed=TAURI_CONFIG");
    let library_development = env::var_os("CARGO_FEATURE_LIBRARY_DEV_SURFACE").is_some();
    let preview = env::var_os("CARGO_FEATURE_PREVIEW_SURFACE").is_some();
    let settings_reference = env::var_os("CARGO_FEATURE_SETTINGS_REFERENCE").is_some();
    if settings_reference && (library_development || preview) {
        panic!("the Settings reference is isolated from the product and library surfaces");
    }
    let mode = BuildMode::from_enabled_features(library_development, preview)
        .expect("only one Local Meeting Notes surface feature may be enabled");
    let mut config = fs::read_to_string("tauri.conf.json")
        .and_then(|value| serde_json::from_str(&value).map_err(Into::into))
        .expect("failed to read active Tauri configuration");
    if let Ok(override_source) = env::var("TAURI_CONFIG") {
        let override_value = serde_json::from_str(&override_source)
            .expect("failed to read Tauri configuration override");
        merge_config(&mut config, override_value);
    }
    let plan = if settings_reference {
        settings_reference_contract::validate(&config)
            .expect("Settings-reference feature/config isolation failed");
        settings_reference_contract::plan()
    } else {
        validate(mode, &config).expect("Tauri feature/config isolation failed");
        plan(mode)
    };
    println!("cargo:rerun-if-changed=capabilities");
    println!("cargo:rerun-if-changed=permissions");
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(
                tauri_build::AppManifest::new()
                    .commands(plan.commands)
                    .permissions_path_pattern(plan.permissions_path),
            )
            .capabilities_path_pattern(plan.capabilities_path),
    )
    .expect("failed to build Local Meeting Notes shell metadata")
}
