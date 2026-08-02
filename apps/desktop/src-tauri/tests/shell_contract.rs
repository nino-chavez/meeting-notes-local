use serde_json::Value;

#[test]
fn single_instance_is_the_first_plugin_and_precedes_app_setup() {
    let source = include_str!("../src/main.rs");
    let plugin = source
        .find(".plugin(tauri_plugin_single_instance::init")
        .expect("single-instance plugin registration");
    let setup = source.find(".setup(|app|").expect("startup setup hook");

    assert_eq!(source.find(".plugin("), Some(plugin));
    assert!(plugin < setup);
    assert!(source.contains("get_webview_window(ACTIVE_WINDOW_LABEL)"));
}

#[test]
fn generated_preview_library_buttons_bind_their_own_activation() {
    let shell = include_str!("../../ui/main.js");

    assert!(
        shell.contains("button.addEventListener(\"click\", () => openMeetingDetail(row.handle));")
    );
    assert!(shell.contains(
        "button.addEventListener(\"click\", () => openLibrarySearchResult(result.handle));"
    ));
    assert!(
        shell
            .contains("row.transcriptAvailable ? \"Open meeting\" : \"No transcript was created\"")
    );
    assert!(!shell.contains("Transcript unavailable"));
    assert!(!shell.contains("libraryList.addEventListener(\"click\""));
    assert!(!shell.contains("librarySearchResults.addEventListener(\"click\""));
}

#[test]
fn meeting_detail_status_helper_is_defined_before_use() {
    let shell = include_str!("../../ui/main.js");
    let helper = shell
        .find("function message(target, text, state = \"\")")
        .expect("meeting-detail status helper");
    let first_call = shell
        .find("message(meetingDetailState")
        .expect("meeting-detail status call");

    assert!(helper < first_call);
    assert!(shell[helper..first_call].contains("target.dataset.state = state;"));
}

#[test]
fn transcript_only_fallback_requires_a_current_transcript_handle() {
    let shell = include_str!("../../ui/main.js");

    assert!(shell.contains("[\"transcript-only\", \"summary-failed\"].includes(response.state)"));
    assert!(shell.contains("&& Boolean(response.transcriptHandle);"));
    assert!(shell.contains("meetingNoNote.hidden = !showsTranscriptFallback;"));
    assert!(!shell.contains("meetingNoNote.hidden = false;"));
}

#[test]
fn main_window_has_only_named_commands_and_no_generic_capability() {
    let capability: Value =
        serde_json::from_str(include_str!("../capabilities/main.json")).unwrap();
    assert_eq!(capability["windows"], serde_json::json!(["main"]));
    assert_eq!(
        capability["permissions"],
        serde_json::json!([
            "allow-app-snapshot",
            "allow-start-meeting",
            "allow-stop-meeting",
            "allow-dismiss-meeting",
            "allow-retry-startup"
        ])
    );
    assert!(capability.get("remote").is_none());
    let serialized = serde_json::to_string(&capability).unwrap();
    for forbidden in ["shell:", "fs:", "process:", "dialog:", "http:"] {
        assert!(
            !serialized.contains(forbidden),
            "forbidden capability {forbidden}"
        );
    }
}

#[test]
fn preview_window_is_a_separate_real_capture_shell_with_a_read_only_library() {
    let preview: Value = serde_json::from_str(include_str!("../tauri.preview.conf.json")).unwrap();
    let capability: Value =
        serde_json::from_str(include_str!("../capabilities/preview.json")).unwrap();
    let production: Value = serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
    let package: Value = serde_json::from_str(include_str!("../../package.json")).unwrap();

    assert_eq!(preview["productName"], "Local Meeting Notes Preview");
    assert_eq!(
        preview["identifier"],
        "com.ninochavez.local-meeting-notes.preview"
    );
    assert_eq!(preview["build"]["frontendDist"], "../ui");
    assert_eq!(preview["app"]["windows"][0]["label"], "preview");
    assert_eq!(
        preview["app"]["windows"][0]["title"],
        "Local Meeting Notes — Preview"
    );
    assert_eq!(
        preview["app"]["security"]["capabilities"],
        serde_json::json!(["preview-window"])
    );
    assert_eq!(
        preview["bundle"]["resources"],
        production["bundle"]["resources"]
    );
    assert_eq!(preview["bundle"]["macOS"]["signingIdentity"], "-");
    assert!(
        package["scripts"]["preview"]
            .as_str()
            .is_some_and(|script| script.contains("tauri.preview.conf.json")
                && script.contains("preview-surface"))
    );
    assert!(
        package["scripts"]["preview-build"]
            .as_str()
            .is_some_and(|script| script.contains("tauri.preview.conf.json")
                && script.contains("preview-surface")
                && script.contains("prepare-preview-bundle.sh sign"))
    );
    assert!(
        package["scripts"]["preview-verify"]
            .as_str()
            .is_some_and(|script| script.contains("prepare-preview-bundle.sh verify"))
    );
    let preview_preparer = include_str!("../../../../scripts/prepare-preview-bundle.sh");
    assert!(preview_preparer.contains("capture-entitlements.plist"));
    assert!(preview_preparer.contains("meeting-capture"));
    assert!(preview_preparer.contains("build_manifest.py"));
    assert!(preview_preparer.contains("codesign --verify --deep --strict"));
    assert!(preview_preparer.contains("com\\.apple\\.security\\.device\\.audio-input"));
    assert_eq!(capability["windows"], serde_json::json!(["preview"]));
    assert_eq!(
        capability["permissions"],
        serde_json::json!([
            "allow-app-snapshot",
            "allow-start-meeting",
            "allow-stop-meeting",
            "allow-dismiss-meeting",
            "allow-retry-startup",
            "allow-preview-library-snapshot",
            "allow-preview-library-search",
            "allow-preview-library-open-search-result",
            "allow-preview-library-open-note",
            "allow-preview-library-open-evidence",
            "allow-preview-library-open-transcript"
        ])
    );
    let serialized = serde_json::to_string(&capability).unwrap();
    for forbidden in ["shell:", "fs:", "process:", "dialog:", "http:"] {
        assert!(
            !serialized.contains(forbidden),
            "forbidden preview capability {forbidden}"
        );
    }
}

#[test]
fn product_operation_facade_remains_unregistered() {
    let source = include_str!("../src/main.rs");
    let handler_start = source
        .find(".invoke_handler(tauri::generate_handler![")
        .expect("named command handler");
    let handler_end = source[handler_start..]
        .find("])")
        .expect("named command handler end")
        + handler_start;
    let handler = &source[handler_start..handler_end];

    assert!(source.contains("mod product_facade;"));
    assert!(!handler.contains("restore_withheld_turn"));
    assert!(!handler.contains("regenerate_note"));
}

#[test]
fn private_library_reader_has_no_registered_command_or_storage_authority() {
    let main = include_str!("../src/main.rs");
    let reader = include_str!("../src/library_reader.rs");
    let handler_start = main
        .find(".invoke_handler(tauri::generate_handler![")
        .expect("named command handler");
    let handler_end = main[handler_start..]
        .find("])")
        .expect("named command handler end")
        + handler_start;

    assert!(main.contains("mod library_reader;"));
    assert!(!main[handler_start..handler_end].contains("library_reader"));
    assert!(!reader.contains("#[tauri::command]"));
    assert!(!reader.contains("tauri::"));
    assert!(!reader.contains("StorageRoot::create"));
    assert!(!reader.contains("invoke_handler"));
}

#[test]
fn product_operation_facade_uses_top_level_frozen_ui_arguments() {
    let facade = include_str!("../src/product_facade.rs");

    assert_eq!(
        facade
            .matches("#[tauri::command(rename_all = \"camelCase\")]")
            .count(),
        2
    );
    assert!(facade.contains(
        "fn restore_withheld_turn(\n    meeting_id: Uuid,\n    source_transcript_sha256: String,\n    source_turn_index: u32,"
    ));
    assert!(facade.contains(
        "fn regenerate_note(\n    meeting_id: Uuid,\n    source_transcript_sha256: String,"
    ));
    assert!(!facade.contains("fn restore_withheld_turn(\n    args:"));
    assert!(!facade.contains("fn regenerate_note(\n    args:"));
}

#[test]
fn bundled_shell_uses_restrictive_local_csp() {
    let config: Value = serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
    let security = &config["app"]["security"];
    assert_eq!(security["capabilities"], serde_json::json!(["main-window"]));
    assert_eq!(security["freezePrototype"], true);
    let csp = security["csp"].as_str().unwrap();
    assert!(csp.contains("default-src 'self'"));
    assert!(csp.contains("object-src 'none'"));
    assert!(csp.contains("form-action 'none'"));
    assert!(!csp.contains("https:"));
    assert!(!csp.contains("*"));
}

#[test]
fn shell_renders_safe_state_before_runtime_preflight() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");
    assert!(html.contains("data-startup-state=\"shell-rendered\""));
    assert!(html.contains("Nothing is recording"));
    assert!(html.contains("The window opens before any audio or model process starts."));
    for command in [
        "app_snapshot",
        "start_meeting",
        "stop_meeting",
        "dismiss_meeting",
        "retry_startup",
    ] {
        assert!(script.contains(&format!("invoke(\"{command}\"")));
    }
    assert!(!script.contains("innerHTML"));
    assert!(!script.contains("Internal beta"));
    assert!(!script.contains("Command.sidecar"));
    assert!(!script.contains("window.__TAURI__.fs"));
}

#[test]
fn preview_library_pauses_capture_polling_and_resumes_on_return() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");

    assert!(html.contains("id=\"library-link\""));
    assert!(html.contains("id=\"library-screen\""));
    assert!(html.contains("id=\"library-transcript-screen\""));
    assert!(html.contains("id=\"meeting-detail-screen\""));
    assert!(html.contains("id=\"library-search\""));
    assert!(script.contains("libraryViewActive = true"));
    assert!(script.contains("if (libraryViewActive) return;"));
    assert!(script.contains("libraryViewActive = false;\n  refresh();"));
    assert!(script.contains("preview_library_snapshot"));
    assert!(script.contains("preview_library_search"));
    assert!(script.contains("preview_library_open_search_result"));
    assert!(script.contains("preview_library_open_note"));
    assert!(script.contains("preview_library_open_evidence"));
    assert!(script.contains("preview_library_open_transcript"));
}

#[test]
fn preview_library_navigation_rebuilds_one_current_handle_generation() {
    let script = include_str!("../../ui/main.js");

    assert!(script.contains("async function rebuildLibraryView(resetSearch = false)"));
    assert!(script.contains("const snapshot = await invoke(\"preview_library_snapshot\");"));
    assert!(script.contains("if (query) {\n      libraryList.replaceChildren();\n      renderLibrarySearch(await invoke(\"preview_library_search\", { query }));"));
    assert!(script.contains("async function returnToLibrary()"));
    assert!(script.contains("await rebuildLibraryView(false);"));
    assert!(script.contains("await rebuildLibraryView(true);"));
    assert!(
        script.contains("library-transcript-back\").addEventListener(\"click\", returnToLibrary)")
    );
    assert!(script.contains("meeting-detail-back\").addEventListener(\"click\", returnToLibrary)"));
    assert!(script.contains("libraryList.replaceChildren();\n  setError(libraryNotice, \"Searching this retained Preview Library…\")"));
    assert!(script.contains("librarySearchResults.replaceChildren();\n  setError(libraryNotice, \"Opening the selected retained result…\")"));
}

#[test]
fn metadata_only_search_results_have_no_transcript_action() {
    let script = include_str!("../../ui/main.js");
    let styles = include_str!("../../ui/styles.css");

    assert!(script.contains(
        "const metadataOnly = result.kind === \"meeting\" && result.transcriptAvailable !== true;"
    ));
    assert!(script.contains("button.disabled = metadataOnly;"));
    assert!(script.contains("? \"No transcript was created\""));
    assert!(!styles.contains("var(--serif)"));
    assert!(
        styles.contains(".meeting-no-note h2 { margin: 0; font-family: ui-serif, Georgia, serif;")
    );
}

#[test]
fn preview_search_is_a_named_read_only_boundary_and_preserves_production_commands() {
    let source = include_str!("../src/main.rs");
    let contract = include_str!("../build_contract.rs");
    let handler_start = source
        .find(".invoke_handler(tauri::generate_handler![")
        .expect("named command handler");
    let handler_end = source[handler_start..]
        .find("])")
        .expect("named command handler end")
        + handler_start;
    let handler = &source[handler_start..handler_end];

    assert!(handler.contains("preview_library_search"));
    assert!(handler.contains("preview_library_open_search_result"));
    assert!(handler.contains("preview_library_open_note"));
    assert!(handler.contains("preview_library_open_evidence"));
    assert!(source.contains("reader.open_search_result(&handle)"));
    assert!(contract.contains("const PRODUCTION_COMMANDS"));
    assert!(
        !contract[contract.find("const PRODUCTION_COMMANDS").unwrap()
            ..contract.find("const PREVIEW_COMMANDS").unwrap()]
            .contains("preview_library_search")
    );
}

#[test]
fn macos_bundle_declares_capture_purposes_and_common_resources() {
    let plist = include_str!("../Info.plist");
    assert!(plist.contains("NSMicrophoneUsageDescription"));
    assert!(plist.contains("NSAudioCaptureUsageDescription"));
    assert!(plist.contains("meetings you start"));
    assert!(plist.contains("local transcript"));
    assert!(!plist.contains("local notes"));

    let html = include_str!("../../ui/index.html");
    assert!(html.contains("deletion runs the next time it opens"));

    let config: Value = serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
    assert_eq!(config["bundle"]["macOS"]["minimumSystemVersion"], "14.4");
    assert_eq!(
        config["bundle"]["resources"]["../runtime/app-runtime.json"],
        "app-runtime.json"
    );
    assert_eq!(
        config["bundle"]["icon"],
        serde_json::json!(["icons/icon.png"])
    );

    let boundary: Value =
        serde_json::from_str(include_str!("../tauri.boundary.conf.json")).unwrap();
    assert_eq!(boundary["bundle"]["macOS"]["signingIdentity"], "-");
    assert!(boundary["bundle"].get("resources").is_none());
}
