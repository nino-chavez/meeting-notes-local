mod build_contract;

use std::{env, fs};

use build_contract::{BuildMode, plan, validate};

fn main() {
    let mode = BuildMode::from_enabled_features(
        env::var_os("CARGO_FEATURE_LIBRARY_DEV_SURFACE").is_some(),
        env::var_os("CARGO_FEATURE_PREVIEW_SURFACE").is_some(),
    )
    .expect("only one Local Meeting Notes surface feature may be enabled");
    let config = env::var("TAURI_CONFIG")
        .ok()
        .map(Ok)
        .unwrap_or_else(|| fs::read_to_string("tauri.conf.json"))
        .and_then(|value| serde_json::from_str(&value).map_err(Into::into))
        .expect("failed to read active Tauri configuration");
    validate(mode, &config).expect("Tauri feature/config isolation failed");
    let plan = plan(mode);
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
