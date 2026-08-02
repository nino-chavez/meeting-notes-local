fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "app_snapshot",
            "start_meeting",
            "stop_meeting",
            "dismiss_meeting",
            "retry_startup",
            "library_dev_snapshot",
            "library_dev_search",
            "library_dev_open_note",
            "library_dev_open_evidence",
        ]),
    ))
    .expect("failed to build Local Meeting Notes shell metadata")
}
