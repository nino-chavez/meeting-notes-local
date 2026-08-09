pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("Yawn synthetic UI review shell failed");
}
