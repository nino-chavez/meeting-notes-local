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
    assert!(
        shell.contains("const row = document.createElement(metadataOnly ? \"div\" : \"button\");")
    );
    assert!(shell.contains("row.transcriptAvailable ? \"Open meeting\" : \"Open details\""));
    // The row's subtitle is composed from the label source, because the label
    // is now one of three things. When there is no title the capture time *is*
    // the label, so the subtitle must not repeat it.
    assert!(shell.contains("const captured = formatMeetingTime(row.createdAtEpochSeconds);"));
    assert!(shell.contains("if (labelSource !== \"date\") notes.push(captured);"));
    assert!(shell.contains("if (labelSource === \"derived\") notes.push(\"Opening line\");"));
    assert!(shell.contains("if (!row.transcriptAvailable) notes.push(\"No transcript\");"));
    assert!(
        !shell.contains("Untitled meeting"),
        "every meeting read this, all of them at once, until auto-titling"
    );
    assert!(!shell.contains("Transcript unavailable"));
    assert!(!shell.contains("libraryList.addEventListener(\"click\""));
    // Renaming is offered only when the record's revision is known. A null
    // revision means it could not be read, and writing over a record you could
    // not read is what the conflict check exists to prevent.
    assert!(shell.contains("if (Number.isInteger(snapshot.metadataRevision)) {"));
    assert!(shell.contains("invoke(\"library_set_meeting_title\", {"));
    // An empty answer clears the operator's title rather than storing one, and
    // the prompt says so rather than leaving it to be discovered.
    assert!(shell.contains("answer.trim() === \"\" ? null : answer"));
    assert!(shell.contains("Leave it empty to go back to its opening line."));

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
    assert!(shell.contains("Transcript available. Automatic notes are not available yet."));
    assert!(shell.contains("Meeting details are available. No transcript was created."));
}

#[test]
fn transcript_only_fallback_requires_a_current_transcript_handle() {
    let navigation = include_str!("../../ui/navigation-state.mjs");

    assert!(
        navigation.contains("const transcriptAvailable = Boolean(response?.transcriptHandle);")
    );
    assert!(navigation.contains("response?.state === \"transcript-only\" && !transcriptAvailable"));
    assert!(navigation.contains("response?.state === \"summary-failed\" && !transcriptAvailable"));
    assert!(navigation.contains("canOpenTranscript: transcriptAvailable"));
}

#[test]
fn main_window_has_only_named_commands_and_no_generic_capability() {
    let capability: Value =
        serde_json::from_str(include_str!("../capabilities/main.json")).unwrap();
    assert_eq!(capability["windows"], serde_json::json!(["main"]));
    // The shipped internal-alpha surface: the same reviewed command set the
    // Preview window carries, decided 2026-08-04 after the 0.2.0 cohort DMG
    // proved the narrower list left the shell without record or search.
    // The guided sitting recorder (start/stop) joined the same day by the
    // operator's enrollment-registration decision, and the measured
    // operating-point review with profile build/publication joined
    // 2026-08-05 with the profile-build decision. Note generation remains
    // absent from both windows.
    assert_eq!(
        capability["permissions"],
        serde_json::json!([
            "allow-app-snapshot",
            "allow-start-meeting",
            "allow-stop-meeting",
            "allow-dismiss-meeting",
            "allow-retry-startup",
            // First run (§ H), registered 2026-08-06. These three read and request
            // the two capture permissions through the manifest-verified probe.
            // They hold no storage authority and read no operator content, and
            // they are granted in both windows because first run is not a Preview
            // feature — a shipped build that cannot report its own permissions has
            // the same lying surface a Preview one would.
            "allow-first-run-permissions",
            "allow-first-run-request-microphone",
            "allow-first-run-request-system-audio",
            "allow-preview-profile-snapshot",
            "allow-preview-enrollment-surface",
            "allow-preview-enrollment-start-sitting",
            "allow-preview-enrollment-stop-sitting",
            "allow-preview-enrollment-operating-points",
            "allow-preview-enrollment-build-profile",
            "allow-preview-profile-preserve-legacy",
            "allow-preview-profile-reset",
            "allow-preview-library-snapshot",
            "allow-preview-retention-overview",
            "allow-preview-library-search",
            "allow-preview-library-open-search-result",
            "allow-preview-library-open-note",
            "allow-preview-library-open-evidence",
            "allow-preview-library-open-transcript",
            "allow-preview-delete-meeting-audio",
            // Separate grant from the audio one, because removing a whole
            // meeting destroys the retained transcript rather than freeing
            // disk space, and one grant must not imply the other.
            "allow-preview-delete-meeting",
            // Five separate grants, not one. A window allowed to rename a
            // meeting is not thereby allowed to delete a folder, and the
            // capability list is where that distinction is visible.
            "allow-library-create-folder",
            "allow-library-rename-folder",
            "allow-library-delete-folder",
            "allow-library-assign-meeting-folder",
            "allow-library-set-meeting-title",
            "allow-restore-withheld-turn",
            "allow-refresh-current-transcript",
            "allow-operator-note",
            "allow-save-operator-note"
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
fn shipped_shell_is_permitted_every_command_it_invokes() {
    // The 0.2.0 cohort DMG proved the failure mode this pins: the shell is one
    // artifact shared by both lanes, and it shipped invoking commands the main
    // window's capability never granted — record and search were unreachable on
    // every machine while the mechanical release suite stayed green. Every
    // command the shell invokes must be permitted by BOTH window capabilities.
    let script = include_str!("../../ui/main.js");
    let mut invoked: Vec<String> = script
        .match_indices("invoke(\"")
        .map(|(at, _)| {
            let rest = &script[at + "invoke(\"".len()..];
            rest[..rest.find('"').expect("unterminated invoke name")].to_string()
        })
        .collect();
    invoked.sort();
    invoked.dedup();
    assert!(
        invoked.iter().any(|command| command == "start_meeting"),
        "the shipped shell no longer reaches Start recording at all"
    );
    for (name, source) in [
        ("main", include_str!("../capabilities/main.json")),
        ("preview", include_str!("../capabilities/preview.json")),
    ] {
        let capability: Value = serde_json::from_str(source).unwrap();
        let permissions: Vec<String> = capability["permissions"]
            .as_array()
            .expect("permission list")
            .iter()
            .map(|permission| permission.as_str().expect("permission name").to_string())
            .collect();
        for command in &invoked {
            let needed = format!("allow-{}", command.replace('_', "-"));
            assert!(
                permissions.contains(&needed),
                "ui/main.js invokes `{command}` but capabilities/{name}.json \
                 grants no `{needed}`; that window renders a control that \
                 cannot work"
            );
        }
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
            // First run (§ H), registered 2026-08-06. These three read and request
            // the two capture permissions through the manifest-verified probe.
            // They hold no storage authority and read no operator content, and
            // they are granted in both windows because first run is not a Preview
            // feature — a shipped build that cannot report its own permissions has
            // the same lying surface a Preview one would.
            "allow-first-run-permissions",
            "allow-first-run-request-microphone",
            "allow-first-run-request-system-audio",
            "allow-preview-profile-snapshot",
            "allow-preview-enrollment-surface",
            "allow-preview-enrollment-start-sitting",
            "allow-preview-enrollment-stop-sitting",
            "allow-preview-enrollment-operating-points",
            "allow-preview-enrollment-build-profile",
            "allow-preview-profile-preserve-legacy",
            "allow-preview-profile-reset",
            "allow-preview-library-snapshot",
            "allow-preview-retention-overview",
            "allow-preview-library-search",
            "allow-preview-library-open-search-result",
            "allow-preview-library-open-note",
            "allow-preview-library-open-evidence",
            "allow-preview-library-open-transcript",
            "allow-preview-delete-meeting-audio",
            // Separate grant from the audio one, because removing a whole
            // meeting destroys the retained transcript rather than freeing
            // disk space, and one grant must not imply the other.
            "allow-preview-delete-meeting",
            // Five separate grants, not one. A window allowed to rename a
            // meeting is not thereby allowed to delete a folder, and the
            // capability list is where that distinction is visible.
            "allow-library-create-folder",
            "allow-library-rename-folder",
            "allow-library-delete-folder",
            "allow-library-assign-meeting-folder",
            "allow-library-set-meeting-title",
            "allow-restore-withheld-turn",
            "allow-refresh-current-transcript",
            "allow-operator-note",
            "allow-save-operator-note"
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
fn product_operation_facade_registers_restoration_but_not_regeneration() {
    // restore_withheld_turn joined the handler on 2026-08-04 by the
    // operator's correction-surface (J4) decision, backed by the installed
    // DesktopProductCoordinator. regenerate_note stays out: no note
    // generator is admitted, so its coordinator can only refuse, and a
    // rendered control that cannot work is the failure this file exists to
    // prevent.
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
    assert!(handler.contains("product_facade::restore_withheld_turn"));
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
fn withheld_turns_render_positionally_without_meeting_text() {
    let script = include_str!("../../ui/main.js");
    let styles = include_str!("../../ui/styles.css");
    assert!(script.contains("turn.withheld"));
    assert!(script.contains("A voice check withheld this turn's text."));
    // The withheld branch renders its fixed note and never the turn's text
    // field: the gate's decision is visible, the withheld words are not.
    // The restore control (registered 2026-08-04, J4) lives in the same
    // branch and passes the whole turn to its handler, still without ever
    // reading the withheld text.
    let branch = script
        .split("if (turn.withheld) {")
        .nth(1)
        .and_then(|rest| rest.split("continue;").next())
        .expect("withheld render branch exists");
    assert!(!branch.contains("turn.text"));
    assert!(!branch.contains("appendTurnText"));
    assert!(branch.contains("Restore this turn"));
    assert!(script.contains("invoke(\"restore_withheld_turn\""));
    // The restore arguments are the view's own bound identity, never
    // operator-typed values.
    assert!(script.contains("sourceTranscriptSha256: context.currentTranscriptSha256"));
    assert!(script.contains("sourceTurnIndex: turn.sourceTurnIndex"));
    assert!(styles.contains(".withheld-note"));
}

#[test]
fn transcript_warnings_render_one_per_paragraph_and_keep_producer_order() {
    // The producer orders these most serious first, and the first one can say
    // that somebody sitting beside the operator is being removed from a record
    // that cannot be re-made. Joined into a single run of text — which is how
    // this rendered until 2026-08-05 — that sentence arrives spliced to a
    // retention notice and a segment count, and reads as boilerplate.
    let script = include_str!("../../ui/main.js");
    let styles = include_str!("../../ui/styles.css");
    let render = script
        .split("function renderTurns(")
        .nth(1)
        .and_then(|rest| rest.split("for (const turn of").next())
        .expect("the warning render preamble exists");
    assert!(render.contains("warning.replaceChildren("));
    assert!(render.contains("safeWarnings.map("));
    assert!(render.contains("warning-line"));
    // The regression this pins: collapsing the list back into one node.
    assert!(!render.contains("safeWarnings.join("));
    assert!(!render.contains("warning.textContent ="));
    // Order is the producer's, so the view must not sort or filter them.
    assert!(!render.contains("safeWarnings.sort("));
    assert!(!render.contains("safeWarnings.filter("));
    // Still hidden when there is nothing to say.
    assert!(render.contains("warning.hidden = safeWarnings.length === 0"));
    assert!(styles.contains(".warning-line"));
}

#[test]
fn preview_navigation_spine_keeps_idle_polling_and_safe_capture_actions() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");
    let navigation = include_str!("../../ui/navigation-state.mjs");
    let styles = include_str!("../../ui/styles.css");

    assert!(html.contains("id=\"product-nav\""));
    assert!(html.contains("id=\"find-link\" type=\"button\">Find"));
    assert!(html.contains("id=\"meetings-link\""));
    assert!(html.contains("id=\"meetings-link\" type=\"button\">Meetings"));
    assert!(html.contains("id=\"promises-link\" type=\"button\">Promises"));
    assert!(html.contains("id=\"profile-link\" type=\"button\" hidden>Settings"));
    assert!(html.contains("id=\"find-screen\""));
    assert!(html.contains("id=\"meetings-screen\""));
    assert!(html.contains("id=\"promises-screen\""));
    assert!(html.contains("Automatic notes are not available yet."));
    assert!(
        html.contains("this view stays empty instead of guessing promises from transcript words")
    );
    assert!(html.contains("id=\"library-transcript-screen\""));
    assert!(html.contains("id=\"meeting-detail-screen\""));
    assert!(html.contains("id=\"library-search\""));
    assert!(html.contains("id=\"start-meeting-action\""));
    assert!(html.contains("id=\"workflow-return\" type=\"button\" hidden>View progress"));
    assert!(html.contains("id=\"stop-button\" type=\"button\" hidden>Stop recording"));
    assert!(html.contains("id=\"start-back\""));
    assert!(
        styles
            .contains("html[data-screen=\"idle-screen\"] main { padding-bottom: var(--space-8); }")
    );
    assert!(styles.contains("html[data-screen=\"profile-screen\"] main { padding-top: var(--space-8); padding-bottom: var(--space-2); }"));
    assert!(html.contains("id=\"start-meeting-error-screen\""));
    assert!(script.contains("function syncProductNavigation()"));
    assert!(script.contains("for (const [link, destination] of ["));
    assert!(script.contains("link.setAttribute(\"aria-current\", \"page\")"));
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
    assert!(script.contains(
        "const result = await invoke(\"preview_library_open_search_result\", { handle });"
    ));
}

#[test]
fn preview_shell_keeps_navigation_persistent_and_library_navigation_content_free() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");
    let navigation = include_str!("../../ui/navigation-state.mjs");

    assert!(html.contains("id=\"product-nav\" aria-label=\"Meeting memory\" hidden"));
    assert!(html.contains("id=\"profile-link\" type=\"button\" hidden>Settings"));
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
    assert!(script.contains(
        "connectionUncertaintyStatus(lastSnapshot?.capture, {\n    stopFailed: stopCommandFailed,"
    ));
    assert!(script.contains("const snapshotRequestGate = createLatestRequestGate();"));
    assert!(script.contains("const REFRESH_SUPERSEDED = Symbol(\"refresh-superseded\");"));
    assert!(
        navigation.contains("export function createFreshSnapshotOperation(refresh, superseded)")
    );
    assert!(script.contains(
        "const refreshCurrentOperation = createFreshSnapshotOperation(refresh, REFRESH_SUPERSEDED);"
    ));
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
    assert!(script.contains(
        "const snapshot = await invoke(\"stop_meeting\");\n    acceptCommandSnapshot(snapshot);"
    ));
    assert!(script.contains(
        "const snapshot = await invoke(\"retry_startup\");\n  acceptCommandSnapshot(snapshot);"
    ));
    assert!(!script.contains("render({ startup: \"diagnostic-written\", capture: \"idle\""));
    assert!(script.contains("if (currentScreen === id) routeRevision += 1;"));
    assert!(navigation.contains("export function resolvedScreenForSnapshot"));
    assert!(navigation.contains("export function mutableActionPolicy"));
    assert!(navigation.contains("export function headerActionPolicy"));
    assert!(navigation.contains("currentScreen = \"find-screen\""));
    assert!(navigation.contains("\"find-screen\","));
    assert!(navigation.contains("\"promises-screen\","));
    assert!(navigation.contains("export function captureChannelPresentation(state)"));
    assert!(navigation.contains("export function headerStatusPresentation(snapshot)"));
    assert!(script.contains("headerStatusDot.dataset.state = headerStatusPresentation(snapshot);"));
    assert!(script.contains("renderChannelState(micChannel, snapshot.mic_state);"));
    assert!(script.contains("renderChannelState(systemChannel, snapshot.system_state);"));
    assert!(navigation.contains("export function workflowReturnPolicy"));
    assert!(script.contains("workflowReturn.addEventListener(\"click\", returnToWorkflow);"));
    assert!(script.contains(
        "if (lastSnapshot.capture === \"transcript-ready\") renderTranscript(lastSnapshot);"
    ));

    let start = script.find("async function openMeetings(").unwrap();
    let end = script[start..]
        .find("function showStartTransitionError()")
        .unwrap()
        + start;
    let open_library = &script[start..end];
    assert!(open_library.contains("await rebuildMeetingsView();"));
    assert!(!open_library.contains("preview_library_open_"));
    assert!(script.contains("() => invoke(\"preview_library_snapshot\")"));
}

#[test]
fn preview_voice_profile_surface_bounds_legacy_preservation_and_separate_reset() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");
    let navigation = include_str!("../../ui/navigation-state.mjs");

    assert!(html.contains("id=\"profile-link\""));
    assert!(html.contains("id=\"profile-screen\""));
    assert!(html.contains("Record two short sessions of you talking, at least an hour apart"));
    assert!(html.contains("it does not name speakers"));
    assert!(html.contains("id=\"profile-setup\" type=\"button\" disabled>Set up voice profile"));
    assert!(script.contains("await invoke(\"preview_profile_snapshot\")"));
    assert!(script.contains("await invoke(\"preview_profile_preserve_legacy\")"));
    assert!(script.contains("await invoke(\"preview_profile_reset\", { confirmed: true })"));
    assert!(script.contains("baseline-ready"));
    assert!(script.contains("profilePresent"));
    assert!(script.contains("No profile is set up"));

    // Presence and activation are separate lifecycle facts. The active branch
    // must be tested first, so an enrolled profile can never inherit the
    // preserved-legacy copy promising Preview will not activate what it found.
    assert!(script.contains("profileActive"));
    let active = script.find("snapshot?.profileActive === true").unwrap();
    let preserved = script.find("snapshot?.profilePresent === true").unwrap();
    assert!(
        active < preserved,
        "the active-profile branch must precede the preserved-legacy branch"
    );
    assert!(script.contains("A profile is active."));

    // Guided-enrolment guidance is rendered, and only where it can be acted on.
    assert!(html.contains("id=\"profile-next-step\""));
    assert!(html.contains("id=\"profile-enrollment-gates\""));
    assert!(script.contains("guidedEnrollment"));
    assert!(script.contains("nextStep"));
    assert!(script.contains("snapshot?.profileActive !== true"));
    assert!(script.contains("migration-review-required"));
    assert!(script.contains("Recording stays available"));
    assert!(script.contains("Opening this screen reads only the"));
    assert!(script.contains("adds lifecycle records around the exact stored bytes"));
    assert!(html.contains("id=\"profile-reset-confirmation\""));
    assert!(html.contains("Meetings, transcripts, notes, evidence, and meeting audio remain"));
    assert!(html.contains("logical app-storage deletion, not forensic erasure"));
    assert!(script.contains("showProfileResetConfirmation"));
    assert!(script.contains("The stored voice profile was deleted"));
    assert!(html.contains("It never opens meetings or transcripts"));
    assert!(!script.contains("preview_profile_enroll"));

    // The recorder surface lists per-sitting evidence states and either the
    // honest recording boundary or the working start/stop controls —
    // registered 2026-08-04 by the operator's enrollment-registration
    // decision. Its only mutations are the start/stop pair; "saved" copy
    // must state the deletion that the store's terminal receipt guarantees,
    // and a comparison recording requires a named permitted source whose
    // copy carries the consent boundary.
    assert!(html.contains("id=\"profile-recorder-entry\""));
    assert!(html.contains("id=\"profile-sittings\""));
    assert!(html.contains("id=\"sitting-form\""));
    assert!(html.contains("id=\"sitting-start\""));
    assert!(html.contains("id=\"sitting-stop\""));
    assert!(html.contains("value=\"public-or-licensed\""));
    assert!(html.contains("value=\"consenting-person\""));
    assert!(html.contains("never permission to record someone"));
    assert!(script.contains("preview_enrollment_surface"));
    assert!(script.contains("invoke(\"preview_enrollment_start_sitting\""));
    assert!(script.contains("invoke(\"preview_enrollment_stop_sitting\""));
    assert!(script.contains("enrollmentRecorderPresentation"));
    assert!(navigation.contains("recordingUnavailableReason"));
    assert!(navigation.contains("lastOutcome"));
    assert!(navigation.contains("attemptActive"));
    assert!(script.contains("Saved. The temporary recording has been deleted."));
    assert!(script.contains("does not count toward setup"));
    assert!(!script.contains("preview_enrollment_begin"));
    assert!(!script.contains("preview_enrollment_abandon"));

    // § I choosing-operating-point (registered 2026-08-05): two or three
    // ordered named options carrying both measured costs, radios shipped
    // disabled until measurements load, no row checked in advance, and the
    // build bound to the exact reviewed measurements by digest. The screen
    // never asks for a number.
    assert!(html.contains("id=\"profile-operating-points\""));
    assert!(html.contains("id=\"operating-points-rows\" disabled"));
    assert!(html.contains("id=\"operating-points-build\" type=\"submit\" disabled"));
    assert!(html.contains("Nothing is chosen for you") || html.contains("nothing is chosen for you"));
    assert!(script.contains("invoke(\"preview_enrollment_operating_points\""));
    assert!(script.contains("invoke(\"preview_enrollment_build_profile\""));
    assert!(script.contains("choicesSha256: selection.choicesSha256"));
    assert!(!script.contains("input.checked = true"));
    assert!(!html.contains("name=\"operating-point\""));
    assert!(navigation.contains("Preserve more of my speech"));
    assert!(navigation.contains("Keep more other voices out"));
    assert!(navigation.contains("Measured middle point"));
    assert!(!script.contains("type=\"number\""));
    assert!(!html.contains("type=\"number\""));
}

#[test]
fn tauri_build_tracks_the_active_configuration() {
    let build = include_str!("../build.rs");
    assert!(build.contains("cargo:rerun-if-env-changed=TAURI_CONFIG"));
}

#[test]
fn preview_library_navigation_refreshes_response_scoped_handle_generations() {
    let script = include_str!("../../ui/main.js");
    let navigation = include_str!("../../ui/navigation-state.mjs");

    assert!(script.contains("async function rebuildMeetingsView()"));
    assert!(script.contains("const snapshot = await initializeLibraryReader();"));
    assert!(!script.contains("latestLibrarySnapshot"));
    assert!(script.contains("async function openFind("));
    assert!(script.contains("async function openMeetings("));
    assert!(script.contains("async function openPromises("));
    assert!(script.contains("async function returnToProductHome()"));
    assert!(script.contains("await openMeetings();"));
    assert!(script.contains("await openFind();"));
    assert!(script.contains("await openPromises();"));
    assert!(script.contains(
        "library-transcript-back\").addEventListener(\"click\", returnFromLibraryTranscript)"
    ));
    assert!(
        script.contains("meeting-detail-back\").addEventListener(\"click\", returnToProductHome)")
    );
    assert!(script.contains("setError(libraryNotice, \"Searching your retained meetings…\")"));
    assert!(navigation.contains("export async function refreshFindGeneration(query, actions)"));
    assert!(
        script.contains("const findRefreshOperation = createSingleFlight(performFindRefresh);")
    );
    assert!(
        script
            .contains("librarySearchSubmit.disabled = findNavigationBusy || handleNavigationBusy;")
    );
    assert!(
        !script
            .contains("for (const link of [findLink, meetingsLink, promisesLink]) link.disabled")
    );
    assert!(script.contains(
        "const ownsRoute = () => currentScreen === \"find-screen\" && routeRevision === revision;"
    ));
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
    assert!(!open_result.contains("librarySearchQuery.value = \"\""));

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

    // Globbed rather than named, so a new shell test file runs by existing.
    // Widened 2026-08-07 when the reference check was added: a suite that lists
    // one file by name silently stops covering everything written after it.
    assert_eq!(package["scripts"]["test:ui"], "node --test ui/*.test.mjs");
    assert!(html.contains("id=\"new-meeting\" type=\"button\">Return to Find"));
    // Copy is offered above each transcript, never only after it, and the
    // copied text keeps withheld turns rather than handing over a transcript
    // that reads complete while the app knows it is not.
    assert!(html.contains("id=\"transcript-copy\" type=\"button\">Copy transcript"));
    assert!(html.contains("id=\"library-transcript-copy\" type=\"button\">Copy transcript"));
    assert!(navigation.contains("export function transcriptPlainText"));
    assert!(navigation.contains("(withheld — a voice check set this turn aside)"));
    assert!(script.contains("navigator.clipboard.writeText(text)"));
    assert!(html.contains("id=\"recover-button\" type=\"button\">Return to Find"));
    assert!(!html.contains("Return to Start"));
    assert!(script.contains("let productRootScreen = \"find-screen\";"));
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
    let admission = settlement
        .find("if (!isDismissalReadySnapshot(snapshot)) return false;")
        .unwrap();
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
    assert!(open.contains(
        "if (lastSnapshot?.capture === \"idle\" && !isDismissalReadySnapshot(lastSnapshot)) return;"
    ));
    assert!(open.contains("showStartTransitionError()"));

    let dismiss_start = script
        .find("async function dismissAttemptAndReturnFind")
        .unwrap();
    let dismiss_end = script[dismiss_start..]
        .find("async function returnToFindAfterStartError")
        .unwrap()
        + dismiss_start;
    let dismiss_attempt = &script[dismiss_start..dismiss_end];
    let shared_dismiss = dismiss_attempt
        .find("await dismissMeetingOperation.run()")
        .unwrap();
    let settlement = dismiss_attempt
        .find("const admitted = settleDismissal(snapshot, {")
        .unwrap();
    assert!(shared_dismiss < settlement);
    assert!(dismiss_attempt.contains("const snapshot = await dismissMeetingOperation.run();"));
    assert!(dismiss_attempt.contains("afterOwnedDismiss: invalidateLibraryHandles,"));
    assert!(script.contains("(event) => returnToFindAfterStartError(event.currentTarget)"));
    let return_start = script
        .find("async function returnToFindAfterStartError")
        .unwrap();
    let return_end = script[return_start..]
        .find("for (const field of checks)")
        .unwrap()
        + return_start;
    let return_to_find = &script[return_start..return_end];
    assert!(return_to_find.contains("if (control) control.disabled = true;"));
    assert!(return_to_find.contains("if (control) control.disabled = false;"));
}

#[test]
fn meetings_screen_carries_the_standing_retention_overview() {
    // §K's standing statement: what recording audio is held, how much, and
    // until when. Rows are facts, not navigation — the library list below
    // opens meetings, and deletion stays behind each meeting's reviewed
    // two-step path.
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");

    assert!(html.contains("id=\"retention-overview\""));
    assert!(html.contains("id=\"retention-overview-total\""));
    assert!(html.contains("id=\"retention-overview-rows\""));
    assert!(html.contains("Deleting a recording is reviewed inside its meeting."));
    assert!(script.contains("invoke(\"preview_retention_overview\""));

    let start = script
        .find("function renderRetentionOverview")
        .expect("retention overview renderer");
    let end = script[start..]
        .find("async function refreshRetentionOverview")
        .expect("retention overview refresh")
        + start;
    let renderer = &script[start..end];
    assert!(!renderer.contains("createElement(\"button\")"));
    assert!(renderer.contains("retentionDeadlineMessage"));
    assert!(renderer.contains("Kept until you delete the recording."));
    assert!(renderer.contains("Audio deleted. The transcript, note, and evidence remain."));
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

/// § G whole-meeting deletion. Pinned separately from audio release because the
/// two must never collapse into one control: releasing audio keeps the retained
/// transcript, and this destroys it.
#[test]
fn whole_meeting_deletion_is_a_separate_twice_confirmed_control() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");

    // Two distinct controls with two distinct handles.
    assert!(html.contains("id=\"meeting-delete-review\""));
    assert!(html.contains("id=\"meeting-delete-confirm\""));
    assert!(html.contains("Delete this meeting"));
    assert!(html.contains("Permanently delete meeting"));
    assert!(script.contains("meetingDeletionHandle"));
    assert!(script.contains("meetingAudioDeletionHandle"));

    // The copy must say what is destroyed. "Deletes this meeting" alone would
    // let an operator believe the transcript survives, as it does for audio.
    assert!(html.contains("removes the transcript, the note, your own note, and any audio still held"));
    assert!(html.contains("cannot be recreated"));

    // Reveal, then confirm. The first click must not delete anything.
    assert!(script.contains("meetingDeleteReview.addEventListener(\"click\""));
    assert!(script.contains("meetingDeleteConfirm.addEventListener(\"click\", async () =>"));
    assert!(script.contains("await invoke(\"preview_delete_meeting\", { handle, confirmed: true })"));

    // A removed meeting must not leave its detail view open, which would render
    // a meeting that no longer exists.
    let confirm_handler = script
        .find("meetingDeleteConfirm.addEventListener(\"click\", async () =>")
        .expect("meeting deletion confirm handler");
    let handler_body = &script[confirm_handler..];
    let removed = handler_body.find("already-removed").expect("removed branch");
    let navigate = handler_body.find("returnToProductHome()").expect("must leave the detail view");
    assert!(removed < navigate);
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
    assert!(
        script.contains("const row = document.createElement(metadataOnly ? \"div\" : \"button\");")
    );
    assert!(script.contains("row.dataset.state = \"metadata-only\";"));
    assert!(!script.contains("button.disabled = metadataOnly;"));
    assert!(script.contains("? \"No transcript was created\""));
    assert!(!styles.contains("var(--serif)"));
    assert!(styles.contains(".meeting-retention h2, .meeting-no-note h2"));
    assert!(styles.contains("font-family: ui-serif, Georgia, serif;"));
}

#[test]
fn preview_exact_search_lands_on_opened_unicode_scalar_span() {
    let script = include_str!("../../ui/main.js");

    assert!(script.contains("const characters = Array.from(text || \"\");"));
    assert!(script.contains("start: Number.isInteger(result.start) ? result.start : null,"));
    assert!(script.contains("end: Number.isInteger(result.end) ? result.end : null,"));
    assert!(script.contains(
        "await openLibraryTranscript(result.transcriptHandle, exactMatch, null, transition);"
    ));
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
    assert!(handler.contains("preview_profile_preserve_legacy"));
    assert!(handler.contains("preview_profile_reset"));
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

/// Three things about § H that only fail at runtime, and did.
///
/// The screen was shipped on 35753f5 without claiming the route. `workflowOwnsRoute`
/// starts true and the snapshot poll resolves a workflow destination on every tick,
/// so first run was navigated away from within 1500 ms of appearing — unreachable in
/// practice, with every unit test green, because route ownership is shell state that
/// no unit test holds. The same commit shipped two buttons with no listener and two
/// panels whose only control cannot succeed from inside the window.
#[test]
fn first_run_claims_its_route_and_every_panel_can_be_left() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");

    // Taking the screen and giving it back are both explicit.
    assert!(
        script.contains("claimExplicitRoute();\n  showScreen(\"first-run-screen\""),
        "first run must claim the route before showing, or the poller takes it back"
    );
    assert!(
        script.contains("if (currentScreen === \"first-run-screen\") beginWorkflowRoute();"),
        "a startup failure must reclaim the route from first run"
    );
    // And it is considered from a resting, started app rather than from page load.
    assert!(script.contains("void considerFirstRun();"));
    assert!(!script.contains("enterFirstRunIfIncomplete"));

    let section = html
        .split_once("id=\"first-run-screen\"")
        .expect("first run screen")
        .1
        .split_once("</section>")
        .expect("first run screen end")
        .0;

    // Every control on the screen is reachable from the shell.
    for element in section.split("<button").skip(1) {
        let id = element
            .split_once("id=\"")
            .expect("every first run button is identified")
            .1
            .split_once('"')
            .expect("terminated id")
            .0;
        assert!(
            script.contains(&format!("\"#{id}\"")),
            "{id} is markup no listener refers to"
        );
    }

    // And every step the operator can land on offers a way onward. A panel whose
    // only control retries something it cannot fix is a lockout, and the two that
    // need System Settings or a reinstall are exactly the ones a new operator hits.
    for panel in section.split("data-step-panel=\"").skip(1) {
        let (name, body) = panel.split_once('"').expect("named panel");
        let body = body.split("data-step-panel").next().unwrap_or(body);
        assert!(
            body.contains("<button"),
            "the {name} panel offers the operator nothing to press"
        );
    }
    for (panel, exit) in [
        ("denied-recovery", "first-run-leave-denied"),
        ("unavailable", "first-run-leave-unavailable"),
    ] {
        assert!(
            html.contains(&format!("id=\"{exit}\"")),
            "{panel} must offer an exit that does not depend on the thing that failed"
        );
    }

    // Every id the shell queries exists. Cheap, and it is how the dead buttons
    // would have been caught at the moment they were written.
    for reference in script.split("querySelector(\"#").skip(1) {
        let id = reference.split_once('"').expect("terminated selector").0;
        assert!(
            html.contains(&format!("id=\"{id}\"")),
            "main.js queries #{id}, which no element carries"
        );
    }
}

/// Feature 6's remedy is reachable where the damage is first seen.
///
/// Until now restoration existed only in the Library: the screen shown right
/// after a recording rendered withheld turns with no control, and the cohort
/// handoff told operators to navigate to Meetings to fix it. The gate's worst
/// failure is a colleague beside the operator being cut from a record of a
/// meeting nobody can hold again, and that remedy is worth less the longer it
/// waits — so the delay was the defect.
#[test]
fn the_screen_after_a_recording_can_restore_a_withheld_turn() {
    let script = include_str!("../../ui/main.js");
    let html = include_str!("../../ui/index.html");
    let source = include_str!("../src/main.rs");

    // The recording screen passes a restore callback, not `null`.
    assert!(
        script.contains("attemptTranscriptRestore ? restoreAttemptWithheldTurnAction : null,"),
        "the post-recording transcript renders withheld turns with no way to restore them"
    );
    // Bound to a digest, so a restore can only name the transcript that was read.
    assert!(script.contains("snapshot.current_transcript_sha256"));
    assert!(source.contains("current_transcript_sha256: Option<String>"));
    // And the failure surface is its own element rather than the copy status.
    assert!(html.contains("id=\"transcript-restore-error\""));

    // Restoring publishes a new transcript, so the projection is rebuilt before
    // the next poll — otherwise a second restore names a digest that has moved
    // and is refused as a changed source, on a screen with no refresh.
    assert!(script.contains("invoke(\"refresh_current_transcript\")"));
    assert!(source.contains("fn refresh_current_transcript("));
    // Defined is not registered. Grants are pinned elsewhere, but a command
    // missing from the handler is granted, permitted, and still unreachable —
    // the shell would fail on a restore's refresh with the capability list
    // looking correct.
    let handler_start = source
        .find(".invoke_handler(tauri::generate_handler![")
        .expect("named command handler");
    let handler_end = source[handler_start..]
        .find("])")
        .expect("named command handler end")
        + handler_start;
    assert!(
        source[handler_start..handler_end].contains("refresh_current_transcript"),
        "refresh_current_transcript is defined and granted but never registered"
    );
    // The rebuild refuses a meeting that changed under it, rather than putting
    // one meeting's words under another's heading.
    assert!(source.contains("return Err(\"That transcript is no longer open.\".into());"));

    // Success and redraw are separate sentences. Saying "not restored" after a
    // restore that worked tells the operator to retry something already done.
    assert!(script.contains("The turn was restored. This view could not be refreshed"));
}

/// § D. The operator's own note, and the three ways this surface could lie.
///
/// Brought into v1 by operator decision 2026-08-06; the scope amendment is in
/// `docs/product-definition.md`.
#[test]
fn the_live_note_is_the_operators_alone_and_says_what_it_cannot_do() {
    let html = include_str!("../../ui/index.html");
    let script = include_str!("../../ui/main.js");
    let source = include_str!("../src/main.rs");
    let module = include_str!("../src/operator_note.rs");

    // It is on the recording screen, where the meeting is.
    let recording = html
        .split_once("id=\"recording-screen\"")
        .expect("recording screen")
        .1
        .split_once("</section>\n\n      <section")
        .map(|(body, _)| body)
        .unwrap_or_default();
    assert!(recording.contains("id=\"live-note-text\""));

    // First lie prevented: implying a transcript is being written alongside the
    // typing. Nothing transcribes while a meeting runs, and the screen says so.
    assert!(html.contains("The transcript is made after the meeting ends, not while it runs."));

    // Second: appearing to lose the note when the meeting ends. It is shown back
    // on the finished-transcript screen rather than left on a screen with no way
    // back, and rendered as text, never as markup.
    assert!(html.contains("id=\"transcript-note\""));
    assert!(script.contains("transcriptNoteText.textContent = text;"));
    // And an unreadable note is not shown as no note. Collapsing them would tell
    // an operator they took no notes while the app holds words it could not
    // parse — the same conflation the recording screen already refuses.
    assert!(script.contains("A note was saved for this meeting and could not be read back."));
    assert!(!script.contains("innerHTML"));

    // Third: losing the last thing typed. Review on 128283a found this pin
    // asserted the flush was CALLED, which it was, while the guarantee it names
    // did not hold — so the shape that makes it true is what is pinned now.
    //
    // The saves serialize instead of dropping. `createSingleFlight` coalesces,
    // which is right for a read and silently discards a write; a save arriving
    // during another was dropped, so pressing Stop mid-autosave flushed nothing.
    assert!(script.contains("createWriteQueue("));
    assert!(!script.contains("liveNoteSaving || liveNoteUnreadable"));
    // And the re-entrancy flag closes before the first await, not after it. Set
    // afterwards, a second Stop click passed the guard during the flush and won
    // the race, so the first click's stop failed and painted a red error over a
    // stop that had worked.
    let stop_handler = script
        .split_once("stopButton.addEventListener")
        .expect("stop handler")
        .1;
    let pending_at = stop_handler
        .find("stopCommandPending = true;")
        .expect("re-entrancy flag");
    let flush_at = stop_handler
        .find("await flushLiveNote();")
        .expect("flush before stop");
    assert!(
        pending_at < flush_at,
        "the stop guard must close before the flush awaits, or a second click races it"
    );

    // And what the finished screen shows is what storage confirmed, not what is
    // in the box. Rendering the box meant a dropped save displayed unsaved words
    // as the saved note, and nothing looked wrong until the next launch.
    assert!(script.contains("const text = liveNoteSavedText;"));

    // The note is not evidence and is not stored as evidence: no meeting-record
    // field, a fixed path, replaced atomically. The frozen `meeting/2` contract
    // must stay untouched — a note can never make a meeting unreadable.
    assert!(module.contains("const FILE_NAME: &str = \"operator-note.json\";"));
    assert!(module.contains("durable_replace("));
    assert!(!module.contains("MeetingArtifacts"));

    // Reachable after the meeting is dismissed. Shown only on the transcript
    // screen, the note is readable until the operator navigates away once and
    // then never again — saved, and lost as far as anyone using the app can
    // tell. The retained-meeting screen carries it through the library reader's
    // existing handle discipline, with the unreadable state intact.
    let reader = include_str!("../src/library_reader.rs");
    assert!(reader.contains("pub(crate) operator_note: crate::operator_note::OperatorNote,"));
    assert!(html.contains("id=\"detail-note\""));
    assert!(script.contains("renderDetailNote(response?.operatorNote);"));
    assert!(script.contains("if (note?.unreadable) {"));

    // Neither command takes a meeting identifier from the shell.
    assert!(source.contains("fn operator_note(state: State<'_, ApplicationState>)"));
    assert!(!script.contains("invoke(\"save_operator_note\", { text, meetingId"));
    let handler_start = source
        .find(".invoke_handler(tauri::generate_handler![")
        .expect("named command handler");
    let handler_end = source[handler_start..]
        .find("])")
        .expect("named command handler end")
        + handler_start;
    let handler = &source[handler_start..handler_end];
    assert!(handler.contains("operator_note"));
    assert!(handler.contains("save_operator_note"));
}
