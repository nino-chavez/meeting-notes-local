fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(&["startup_status"])),
    )
    .expect("failed to build Local Meeting Notes shell metadata")
}
