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

    assert!(shell.contains("button.addEventListener(\"click\", () => openMeetingDetail("));
    assert!(shell.contains("row.handle,\n      \"meetings-screen\",\n      button,"));
    assert!(shell.contains(
        "row.addEventListener(\"click\", () => openLibrarySearchResult(result.handle, row));"
    ));
    assert!(shell.contains("const row = document.createElement(metadataOnly ? \"div\" : \"button\");"));
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
    let navigation = include_str!("../../ui/navigation-state.mjs");

    assert!(navigation.contains("const transcriptAvailable = Boolean(response?.transcriptHandle);"));
    assert!(navigation.contains("response?.state === \"transcript-only\" && !transcriptAvailable"));
    assert!(navigation.contains("response?.state === \"summary-failed\" && !transcriptAvailable"));
    assert!(navigation.contains("canOpenTranscript: transcriptAvailable"));
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
fn preview_window_is_a_separate_capture_shell_with_narrow_product_commands() {
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
    assert_eq!(preview["app"]["windows"][0]["width"], 1080);
    assert_eq!(preview["app"]["windows"][0]["height"], 900);
    assert_eq!(preview["app"]["windows"][0]["minWidth"], 800);
    assert_eq!(preview["app"]["windows"][0]["minHeight"], 640);
    assert_eq!(preview["app"]["windows"][0]["resizable"], true);
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
    assert!(preview_preparer.contains("require_note_runtime_absent"));
    assert!(preview_preparer.contains("[[ ! -e \"$path\" && ! -L \"$path\" ]]"));
    for forbidden in [
        "note-bridge.py",
        "note-runtime-project.json",
        "note-validator.zip",
    ] {
        assert!(preview_preparer.contains(forbidden));
    }
    assert!(preview_preparer.contains("codesign --verify --deep --strict"));
    assert!(!preview_preparer.contains(
        "codesign --force --sign \"$identity\" --entitlements \"$ENTITLEMENTS\" \"$MAIN\""
    ));
    assert!(preview_preparer.contains(
        "codesign --force --sign \"$identity\" --entitlements \"$ENTITLEMENTS\" \"$APP\""
    ));
    let capture_sign = preview_preparer
        .find("codesign --force --sign \"$identity\" --entitlements \"$ENTITLEMENTS\" \"$CAPTURE\"")
        .expect("Preview must sign its nested capture helper");
    let metadata_clear = preview_preparer
        .find("xattr -cr \"$APP\"")
        .expect("Preview must clear non-content bundle metadata before signing");
    let manifest_build = preview_preparer
        .find("build_manifest.py\" \"$RESOURCES\" --admission internal-alpha")
        .expect("Preview must rebuild the manifest after signing the helper");
    let app_sign = preview_preparer
        .find("codesign --force --sign \"$identity\" --entitlements \"$ENTITLEMENTS\" \"$APP\"")
        .expect("Preview must sign the enclosing app last");
    let final_verify = preview_preparer
        .rfind("\n  verify_bundle\n")
        .expect("Preview must verify after signing the enclosing app");
    assert!(metadata_clear < capture_sign);
    assert!(capture_sign < manifest_build);
    assert!(manifest_build < app_sign);
    assert!(app_sign < final_verify);
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
            "allow-preview-profile-snapshot",
            "allow-preview-library-snapshot",
            "allow-preview-library-search",
            "allow-preview-library-open-search-result",
            "allow-preview-library-open-note",
            "allow-preview-library-open-evidence",
            "allow-preview-library-open-transcript",
            "allow-preview-delete-meeting-audio"
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
    let production_reader = reader.split("#[cfg(test)]").next().unwrap();
    assert!(!production_reader.contains("StorageRoot::create"));
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
fn preview_navigation_spine_keeps_idle_polling_and_safe_capture_actions() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");
    let navigation = include_str!("../../ui/navigation-state.mjs");
    let styles = include_str!("../../ui/styles.css");

    assert!(html.contains("id=\"product-nav\""));
    assert!(html.contains("id=\"meetings-link\""));
    assert!(html.contains("id=\"meetings-link\" type=\"button\">Library"));
    assert!(html.contains("id=\"profile-link\" type=\"button\">Voice setup"));
    assert!(html.contains("id=\"meetings-screen\""));
    assert!(!html.contains("id=\"find-link\""));
    assert!(!html.contains("id=\"promises-link\""));
    assert!(!html.contains("Promises are not available yet."));
    assert!(html.contains("id=\"library-transcript-screen\""));
    assert!(html.contains("id=\"meeting-detail-screen\""));
    assert!(html.contains("id=\"library-search\""));
    assert!(html.contains("id=\"start-meeting-action\""));
    assert!(html.contains("id=\"workflow-return\" type=\"button\" hidden>View progress"));
    assert!(html.contains("id=\"stop-button\" type=\"button\" hidden>Stop recording"));
    assert!(html.contains("id=\"start-back\""));
    assert!(styles.contains("html[data-screen=\"idle-screen\"] main { padding-bottom: var(--space-8); }"));
    assert!(styles.contains("html[data-screen=\"profile-screen\"] main { padding-top: var(--space-8); padding-bottom: var(--space-2); }"));
    assert!(html.contains("id=\"start-meeting-error-screen\""));
    assert!(script.contains("function syncProductNavigation()"));
    assert!(script.contains("meetingsLink.setAttribute(\"aria-current\", \"page\")"));
    assert!(script.contains("initializeFindInBackground();"));
    assert!(script.contains("const libraryInitialization = createSingleFlight"));
    assert!(navigation.contains("export function createSingleFlight(loader)"));
    assert!(navigation.contains("export async function prepareConsentTransition"));
    assert!(script.contains(
        "function schedulePoll(delay) {\n  if (pollTimer) window.clearTimeout(pollTimer);"
    ));
    assert!(!script.contains("secondaryViewActive"));
    assert!(script.contains("startMeetingAction.addEventListener(\"click\", openStartMeeting);"));
    assert!(script.contains("await invoke(\"start_meeting\", request);"));
    assert!(script.contains("preview_library_snapshot"));
    assert!(script.contains("preview_profile_snapshot"));
    assert!(script.contains("preview_library_search"));
    assert!(script.contains("preview_library_open_search_result"));
    assert!(script.contains("preview_library_open_note"));
    assert!(script.contains("preview_library_open_evidence"));
    assert!(script.contains("preview_library_open_transcript"));
    assert!(script.contains("const result = await invoke(\"preview_library_open_search_result\", { handle });"));
}

#[test]
fn preview_shell_keeps_navigation_persistent_and_library_navigation_content_free() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");
    let navigation = include_str!("../../ui/navigation-state.mjs");

    assert!(html.contains("id=\"product-nav\" aria-label=\"Meeting notes\" hidden"));
    assert!(html.contains("id=\"profile-link\" type=\"button\">Voice setup"));
    assert!(html.contains("id=\"stop-button\" type=\"button\" hidden>Stop recording"));
    assert_eq!(html.matches("id=\"stop-button\"").count(), 1);
    assert!(html.contains("id=\"header-state\" role=\"status\" aria-atomic=\"true\""));
    assert!(html.contains("id=\"header-status-dot\""));
    assert!(html.contains("id=\"mic-channel\" data-state=\"unknown\""));
    assert!(html.contains("id=\"system-channel\" data-state=\"unknown\""));
    assert!(!html.contains("id=\"library-search-results\" role=\"status\""));
    assert!(!html.contains("<main tabindex=\"-1\" aria-live"));
    assert!(script.contains("function renderCaptureAction(snapshot)"));
    assert!(script.contains("productNav.hidden = !policy.showProductNavigation;"));
    assert!(script.contains("stopCommandPending = true;"));
    assert!(script.contains("Recording · Stop needs attention"));
    assert!(script.contains("function renderConnectionUncertainty()"));
    assert!(script.contains("function setHeaderState(text)"));
    assert!(script.contains("changedStatusText(announcedHeaderState, text)"));
    assert!(script.contains("connectionUncertaintyStatus(lastSnapshot?.capture, {\n    stopFailed: stopCommandFailed,"));
    assert!(script.contains("const snapshotRequestGate = createLatestRequestGate();"));
    assert!(script.contains("const REFRESH_SUPERSEDED = Symbol(\"refresh-superseded\");"));
    assert!(navigation.contains("export function createFreshSnapshotOperation(refresh, superseded)"));
    assert!(script.contains("const refreshCurrentOperation = createFreshSnapshotOperation(refresh, REFRESH_SUPERSEDED);"));
    assert!(script.contains("pollTimer = window.setTimeout(refreshCurrent, delay);"));
    assert!(navigation.contains("export function acceptAuthoritativeSnapshot(snapshot, actions)"));
    assert!(navigation.contains("export function isDismissalReadySnapshot(snapshot)"));
    assert!(navigation.contains("export function settleDismissal(snapshot, actions)"));
    assert!(script.contains("function acceptCommandSnapshot(snapshot)"));
    assert!(script.contains("invalidateSnapshotRequests: () => snapshotRequestGate.invalidate(),"));
    assert!(script.contains("const routeOwnership = createRouteOwnershipGate();"));
    assert!(script.contains("function claimExplicitRoute()"));
    assert!(script.contains("const dismissMeetingOperation = createSingleFlight(async () => {"));
    assert!(script.contains("const snapshot = await invoke(\"dismiss_meeting\");\n  return acceptCommandSnapshot(snapshot);"));
    assert!(script.contains("const snapshot = await invoke(\"start_meeting\", request);\n    acceptCommandSnapshot(snapshot);"));
    assert!(script.contains("const snapshot = await invoke(\"stop_meeting\");\n    acceptCommandSnapshot(snapshot);"));
    assert!(script.contains("const snapshot = await invoke(\"retry_startup\");\n  acceptCommandSnapshot(snapshot);"));
    assert!(!script.contains("render({ startup: \"diagnostic-written\", capture: \"idle\""));
    assert!(script.contains("if (currentScreen === id) routeRevision += 1;"));
    assert!(navigation.contains("export function resolvedScreenForSnapshot"));
    assert!(navigation.contains("export function mutableActionPolicy"));
    assert!(navigation.contains("export function headerActionPolicy"));
    assert!(navigation.contains("currentScreen = \"meetings-screen\""));
    assert!(navigation.contains("\"meetings-screen\", \"meeting-detail-screen\", \"profile-screen\""));
    assert!(navigation.contains("export function captureChannelPresentation(state)"));
    assert!(navigation.contains("export function headerStatusPresentation(snapshot)"));
    assert!(script.contains("headerStatusDot.dataset.state = headerStatusPresentation(snapshot);"));
    assert!(script.contains("renderChannelState(micChannel, snapshot.mic_state);"));
    assert!(script.contains("renderChannelState(systemChannel, snapshot.system_state);"));
    assert!(navigation.contains("export function workflowReturnPolicy"));
    assert!(script.contains("workflowReturn.addEventListener(\"click\", returnToWorkflow);"));
    assert!(script.contains("if (lastSnapshot.capture === \"transcript-ready\") renderTranscript(lastSnapshot);"));

    let start = script.find("async function openMeetings()").unwrap();
    let end = script[start..].find("function showStartTransitionError()").unwrap() + start;
    let open_library = &script[start..end];
    assert!(open_library.contains("await rebuildMeetingsView();"));
    assert!(!open_library.contains("preview_library_open_"));
    assert!(script.contains("() => invoke(\"preview_library_snapshot\")"));
}

#[test]
fn preview_voice_profile_surface_is_honest_and_non_mutating() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");

    assert!(html.contains("id=\"profile-link\""));
    assert!(html.contains("id=\"profile-screen\""));
    assert!(html.contains("Two voice sittings, at least one hour apart"));
    assert!(html.contains("A voice profile does not identify speakers"));
    assert!(html.contains("id=\"profile-setup\" type=\"button\" disabled>Set up voice profile"));
    assert!(script.contains("await invoke(\"preview_profile_snapshot\")"));
    assert!(script.contains("setup-unavailable"));
    assert!(script.contains("Voice setup is not available yet"));
    assert!(html.contains("does not open, use, change, or delete it"));
    assert!(!script.contains("preview_profile_reset"));
    assert!(!script.contains("preview_profile_enroll"));
}

#[test]
fn preview_library_navigation_refreshes_response_scoped_handle_generations() {
    let script = include_str!("../../ui/main.js");
    let navigation = include_str!("../../ui/navigation-state.mjs");

    assert!(script.contains("async function rebuildMeetingsView()"));
    assert!(script.contains("const snapshot = await initializeLibraryReader();"));
    assert!(!script.contains("latestLibrarySnapshot"));
    assert!(script.contains("async function openFind()"));
    assert!(script.contains("async function openMeetings()"));
    assert!(script.contains("async function returnToProductHome()"));
    assert!(script.contains("await openMeetings();"));
    assert!(!script.contains("await openFind();"));
    assert!(
        script.contains(
            "library-transcript-back\").addEventListener(\"click\", returnFromLibraryTranscript)"
        )
    );
    assert!(
        script.contains("meeting-detail-back\").addEventListener(\"click\", returnToProductHome)")
    );
    assert!(script.contains("setError(libraryNotice, \"Searching your retained meetings…\")"));
    assert!(navigation.contains("export async function refreshFindGeneration(query, actions)"));
    assert!(
        script.contains("const findRefreshOperation = createSingleFlight(performFindRefresh);")
    );
    assert!(script.contains("librarySearchSubmit.disabled = findNavigationBusy || handleNavigationBusy;"));
    assert!(!script.contains("for (const link of [findLink, meetingsLink, promisesLink]) link.disabled"));
    assert!(script.contains("const ownsRoute = () => currentScreen === \"meetings-screen\" && routeRevision === revision;"));
    assert!(script.contains("if (ownsRoute()) renderLibrarySearch(response);"));
    assert!(
        script
            .contains("libraryList.replaceChildren();\n  librarySearchResults.replaceChildren();")
    );
    assert!(script.contains("meetingClaimList.replaceChildren();"));
    assert!(script.contains("meeting-detail-transcript-handle\").value = \"\""));

    let idle_start = script.find("case \"idle\":").unwrap();
    let idle_end = script[idle_start..].find("case \"arming\":").unwrap() + idle_start;
    let idle = &script[idle_start..idle_end];
    assert!(idle.contains("if (workflowOwnsRoute && currentScreen !== \"idle-screen\") {"));
    assert_eq!(idle.matches("initializeFindInBackground();").count(), 1);

    let refresh_start = script.find("async function performFindRefresh").unwrap();
    let refresh_end = script[refresh_start..]
        .find("async function refreshFindView")
        .unwrap()
        + refresh_start;
    let refresh = &script[refresh_start..refresh_end];
    assert!(
        refresh.find("snapshot: initializeLibraryReader").unwrap()
            < refresh.find("invoke(\"preview_library_search\"").unwrap()
    );
    assert!(refresh.contains("invalidateResults: invalidateLibraryHandles"));

    let wrapper_start = refresh_end;
    let wrapper_end = script[wrapper_start..]
        .find("async function searchLibrary")
        .unwrap()
        + wrapper_start;
    let wrapper = &script[wrapper_start..wrapper_end];
    assert!(
        wrapper.find("setFindRefreshBusy(true)").unwrap()
            < wrapper.find("findRefreshOperation.run()").unwrap()
    );
    assert!(wrapper.contains("finally {\n    setFindRefreshBusy(false);"));

    let open_start = script
        .find("async function openLibrarySearchResult")
        .unwrap();
    let open_end = script[open_start..].find("function schedulePoll").unwrap() + open_start;
    let open_result = &script[open_start..open_end];
    assert!(
        open_result.find("invalidateLibraryHandles()").unwrap()
            < open_result
                .find("invoke(\"preview_library_open_search_result\"")
                .unwrap()
    );
    assert!(open_result.contains("Opening the selected retained result"));
    assert!(!script.contains("librarySearchQuery.value = \"\""));

    for (function, command) in [
        (
            "async function openLibraryTranscript",
            "invoke(\"preview_library_open_transcript\"",
        ),
        (
            "async function openMeetingDetail",
            "invoke(\"preview_library_open_note\"",
        ),
        (
            "async function openMeetingEvidence",
            "invoke(\"preview_library_open_evidence\"",
        ),
        (
            "async function openLibrarySearchResult",
            "invoke(\"preview_library_open_search_result\"",
        ),
    ] {
        let start = script.find(function).unwrap();
        let operation = &script[start..];
        assert!(
            operation.find("invalidateLibraryHandles()").unwrap()
                < operation.find(command).unwrap()
        );
    }
}

#[test]
fn preview_routes_preserve_origin_focus_scroll_and_safe_start_ordering() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");
    let navigation = include_str!("../../ui/navigation-state.mjs");
    let package: Value = serde_json::from_str(include_str!("../../package.json")).unwrap();

    assert_eq!(
        package["scripts"]["test:ui"],
        "node --test ui/navigation-state.test.mjs"
    );
    assert!(html.contains("id=\"new-meeting\" type=\"button\">Return to Library"));
    assert!(html.contains("id=\"recover-button\" type=\"button\">Return to Library"));
    assert!(!html.contains("Return to Start"));
    assert!(script.contains("let productRootScreen = \"meetings-screen\";"));
    assert!(script.contains("productRootScreen = rootForDestination(id, productRootScreen);"));
    assert!(script.contains("screenScrollPositions.set(currentScreen, mainRegion.scrollTop)"));
    assert!(script.contains("heading.focus({ preventScroll: true })"));
    assert!(navigation.contains("return PRODUCT_ROOT_SCREENS.includes(currentRoot)"));
    assert!(navigation.contains("export function restoredScrollPosition"));

    let start = navigation
        .find("export async function prepareConsentTransition")
        .unwrap();
    let transition = &navigation[start..];
    assert!(transition.contains("const snapshot = await actions.dismiss();"));
    let settle_start = navigation.find("export function settleDismissal").unwrap();
    let settlement = &navigation[settle_start..start];
    let hidden_cleanup = settlement.find("actions.clearHiddenAttempt()").unwrap();
    let admission = settlement.find("if (!isDismissalReadySnapshot(snapshot)) return false;").unwrap();
    let visible_cleanup = settlement.find("actions.afterOwnedDismiss()").unwrap();
    assert!(transition.contains("return settleDismissal(snapshot, actions);"));
    assert!(hidden_cleanup < admission && admission < visible_cleanup);
    assert!(script.contains("showScreen(\"start-meeting-error-screen\""));
    assert!(script.contains("startMeetingAction.addEventListener(\"click\", openStartMeeting)"));

    let open_start = script.find("async function openStartMeeting").unwrap();
    let open_end = script[open_start..].find("function renderProfile").unwrap() + open_start;
    let open = &script[open_start..open_end];
    let prepare = open.find("await prepareConsentTransition").unwrap();
    let consent = open.find("showScreen(\"idle-screen\"").unwrap();
    assert!(prepare < consent);
    assert!(open.contains("dismiss: () => dismissMeetingOperation.run()"));
    assert!(open.contains("clearHiddenAttempt: () => clearAttemptReview(true)"));
    assert!(open.contains("afterOwnedDismiss: () => {\n        invalidateLibraryHandles();"));
    assert!(open.contains("if (lastSnapshot?.capture === \"idle\" && !isDismissalReadySnapshot(lastSnapshot)) return;"));
    assert!(open.contains("showStartTransitionError()"));

    let dismiss_start = script.find("async function dismissAttemptAndReturnFind").unwrap();
    let dismiss_end = script[dismiss_start..]
        .find("async function returnToFindAfterStartError")
        .unwrap()
        + dismiss_start;
    let dismiss_attempt = &script[dismiss_start..dismiss_end];
    let shared_dismiss = dismiss_attempt.find("await dismissMeetingOperation.run()").unwrap();
    let settlement = dismiss_attempt.find("const admitted = settleDismissal(snapshot, {").unwrap();
    assert!(shared_dismiss < settlement);
    assert!(dismiss_attempt.contains("const snapshot = await dismissMeetingOperation.run();"));
    assert!(dismiss_attempt.contains("afterOwnedDismiss: invalidateLibraryHandles,"));
    assert!(script.contains("(event) => returnToFindAfterStartError(event.currentTarget)"));
    let return_start = script.find("async function returnToFindAfterStartError").unwrap();
    let return_end = script[return_start..]
        .find("for (const field of checks)")
        .unwrap()
        + return_start;
    let return_to_find = &script[return_start..return_end];
    assert!(return_to_find.contains("if (control) control.disabled = true;"));
    assert!(return_to_find.contains("if (control) control.disabled = false;"));
}

#[test]
fn preview_meeting_detail_requires_two_explicit_steps_for_audio_deletion() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");
    let navigation = include_str!("../../ui/navigation-state.mjs");

    assert!(html.contains("id=\"meeting-retention\""));
    assert!(script.contains("function formatByteSize(bytes)"));
    assert!(script.contains("retentionDeadlineMessage(deadline)"));
    assert!(navigation.contains("export function retentionDeadlineMessage(epochSeconds)"));
    assert!(navigation.contains("Deletion runs while the app is open, or the next time it opens."));
    assert!(navigation.contains(
        "The audio deletion time is unavailable. This Preview cannot show when the audio becomes due."
    ));
    assert!(!navigation.contains("Scheduled to delete"));
    assert!(script.contains("function renderAudioRetention(retention, deletionHandle = \"\")"));
    assert!(script.contains(
        "Retained audio: ${formatByteSize(retention.retainedBytes)} across both recording channels."
    ));
    assert!(script.contains("Kept until you delete the recording."));
    assert!(script.contains("The transcript, note, and evidence remain. You can no longer listen to the recording, check this transcription against it, or transcribe it again. The separate voice profile is unaffected."));
    assert!(html.contains("id=\"recording-delete-review\""));
    assert!(html.contains("Delete recording now"));
    assert!(html.contains("id=\"recording-delete-confirm\""));
    assert!(html.contains("Permanently delete recording"));
    assert!(html.contains("This deletes only this meeting’s local audio."));
    assert!(html.contains("The separate voice profile is unaffected."));
    assert!(script.contains("recordingDeleteReview.addEventListener(\"click\""));
    assert!(script.contains("recordingDeleteConfirm.addEventListener(\"click\", async () =>"));
    assert!(script.contains("await invoke(\"preview_delete_meeting_audio\", { handle })"));
    assert!(!script.contains("window.confirm("));
    assert!(!script.contains("confirm("));
}

#[test]
fn preview_audio_deletion_gates_state_before_handle_authority_or_invalidation() {
    let source = include_str!("../src/main.rs");
    let start = source
        .find("fn preview_delete_meeting_audio(")
        .expect("Preview audio deletion command");
    let end = source[start..]
        .find("fn preview_library_open_evidence(")
        .expect("next Preview command")
        + start;
    let command = &source[start..end];

    let command_lock = command.find("state.command_lock.lock()").unwrap();
    let gate = command
        .find("with_preview_audio_deletion_gate(startup, capture")
        .unwrap();
    let storage = command.find("preview_storage_clone(state)").unwrap();
    let authorize = command.find("reader.authorize_audio_deletion").unwrap();
    let invalidate = command
        .find("with_preview_library_invalidated(state")
        .unwrap();
    let delete = command
        .find(".delete_audio(ManualAudioDeletionUiArgs")
        .unwrap();
    assert!(
        command_lock < gate
            && gate < storage
            && storage < authorize
            && authorize < invalidate
            && invalidate < delete
    );
    assert!(command.contains("if with_preview_library_invalidated(state, || ()).is_err()"));
    assert!(!command.contains(".expect("));
    assert!(source.contains("CaptureState::Idle | CaptureState::TranscriptReady"));
}

#[test]
fn retention_failure_serializes_before_changing_the_model() {
    let source = include_str!("../src/main.rs");
    let start = source
        .find("fn mark_retention_unavailable(state: &ApplicationState)")
        .expect("retention failure transition");
    let end = source[start..]
        .find("fn run_capture_task(")
        .expect("next function")
        + start;
    let transition = &source[start..end];

    let command_lock = transition.find("state.command_lock.lock()").unwrap();
    let model_lock = transition.find("state.model.lock()").unwrap();
    assert!(command_lock < model_lock);
    assert!(!transition.contains(".expect("));
}

#[test]
fn metadata_only_search_results_have_no_transcript_action() {
    let script = include_str!("../../ui/main.js");
    let styles = include_str!("../../ui/styles.css");

    assert!(script.contains(
        "const metadataOnly = result.kind === \"meeting\" && result.transcriptAvailable !== true;"
    ));
    assert!(script.contains("const row = document.createElement(metadataOnly ? \"div\" : \"button\");"));
    assert!(script.contains("row.dataset.state = \"metadata-only\";"));
    assert!(!script.contains("button.disabled = metadataOnly;"));
    assert!(script.contains("? \"No transcript was created\""));
    assert!(!styles.contains("var(--serif)"));
    assert!(styles.contains(".meeting-retention h2, .meeting-no-note h2, .profile-status h2"));
    assert!(styles.contains("font-family: ui-serif, Georgia, serif;"));
}

#[test]
fn preview_exact_search_lands_on_opened_unicode_scalar_span() {
    let script = include_str!("../../ui/main.js");

    assert!(script.contains("const characters = Array.from(text || \"\");"));
    assert!(script.contains("start: Number.isInteger(result.start) ? result.start : null,"));
    assert!(script.contains("end: Number.isInteger(result.end) ? result.end : null,"));
    assert!(script.contains("await openLibraryTranscript(result.transcriptHandle, exactMatch, null, transition);"));
    assert!(script.contains("row.setAttribute(\"aria-label\", `Exact transcript match in turn ${match.sourceTurnIndex + 1}`);"));
    assert!(script.contains("destination?.focus({ preventScroll: true });"));
    assert!(!script.contains("result.text.indexOf"));
}

#[test]
fn preview_transcript_open_rechecks_the_bound_digest_and_path() {
    let source = include_str!("../src/main.rs");
    let reader = include_str!("../src/library_reader.rs");

    assert!(reader.contains("pub(crate) transcript_artifact: Option<ArtifactRef>"));
    assert!(source.contains("reader.open_transcript_bound("));
    assert!(source.contains("meeting.artifacts.current_transcript.as_ref() != Some(expected)"));
    assert!(source.contains("Sha256::digest(&bytes)"));
    assert!(source.contains("current.artifacts.current_transcript.as_ref() != Some(expected)"));
    let sequence = source
        .find("with_meeting_storage_sequence(&coordination")
        .expect("coordinated Preview read");
    let reader_lock = source[sequence..]
        .find("self.preview_library.lock()")
        .expect("Preview reader lock after storage sequence")
        + sequence;
    let load = source
        .find("load_bound_preview_transcript_projection(storage, meeting_id, artifact)")
        .expect("bound transcript load");
    assert!(sequence < reader_lock && reader_lock < load);
    assert!(source[sequence..reader_lock].contains("active_meeting_ids"));
    assert!(reader.contains("if active_meeting_ids.contains(meeting_id)"));
}

#[test]
fn preview_commands_are_named_and_preserve_the_production_command_boundary() {
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
    assert!(handler.contains("preview_profile_snapshot"));
    assert!(handler.contains("preview_library_open_search_result"));
    assert!(handler.contains("preview_library_open_note"));
    assert!(handler.contains("preview_library_open_evidence"));
    assert!(handler.contains("preview_delete_meeting_audio"));
    assert!(source.contains("reader.open_search_result(&handle, active)"));
    assert!(contract.contains("const PRODUCTION_COMMANDS"));
    assert!(
        !contract[contract.find("const PRODUCTION_COMMANDS").unwrap()
            ..contract.find("const PREVIEW_COMMANDS").unwrap()]
            .contains("preview_")
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
