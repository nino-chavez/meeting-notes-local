fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "app_snapshot",
            "start_meeting",
            "stop_meeting",
            "dismiss_meeting",
            "retry_startup",
        ]),
    ))
    .expect("failed to build Local Meeting Notes shell metadata")
}
