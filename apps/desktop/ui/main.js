import {
  canOpenStart,
  captureActivity,
  captureActivityElapsedSeconds,
  captureIsInProgress,
  capturePresentation,
  humanize,
  mergePermissions,
  permissionSummary,
  retentionLabel,
  shouldPollSnapshot,
  transcriptPlainText,
  transcriptTurnsMatching,
  transcriptionWorkerHeartbeatAgeSeconds,
} from "./view-model.mjs";

const root = document.querySelector("#app");
const invoke = window.__TAURI__?.core?.invoke;

const state = {
  activeView: "home",
  busyAction: "",
  consent: { participantsConsented: false, headphones: false, operatorAlone: false },
  error: "",
  library: null,
  meetingManagementOpen: false,
  modal: "",
  notice: "",
  noteDraft: "",
  noteLoadedFor: "",
  noteLoading: false,
  noteSaveQueue: Promise.resolve(),
  noteSaveState: "local",
  noteUnreadable: false,
  permissions: null,
  retentionDays: 7,
  renameDraft: "",
  search: "",
  searchTimer: null,
  selected: null,
  snapshot: null,
  transcriptActionStatus: {},
  transcriptQuery: "",
};

let noteSaveTimer;
let libraryNoteSaveTimer;
let permissionsRefreshTask;
let activityTimer;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function dateLabel(epochSeconds) {
  if (!Number.isFinite(Number(epochSeconds))) return "Saved locally";
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(Number(epochSeconds) * 1000));
}

function timeLabel(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function elapsedAgoLabel(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  return total < 5 ? "just now" : `${timeLabel(total)} ago`;
}

function statusLabel(snapshot, permission) {
  const presentation = capturePresentation(snapshot);
  if (!snapshot) return { label: "Opening", tone: "working" };
  if (snapshot.startup !== "ready") {
    return {
      label: snapshot.startup === "checking" ? "Opening" : "Needs attention",
      tone: snapshot.startup === "checking" ? "working" : "attention",
    };
  }
  if (presentation.capture === "idle" && permissionSummary(permission).state !== "ready") {
    return {
      label: permission ? "Audio setup" : "Checking audio",
      tone: permission ? "attention" : "working",
    };
  }
  if (presentation.capture === "idle") return { label: "Ready", tone: "ready" };
  if (presentation.capture === "recording") return { label: "Recording", tone: "recording" };
  if (presentation.capture === "transcript-ready") return { label: "Ready to read", tone: "complete" };
  return { label: presentation.eyebrow, tone: presentation.tone };
}

function noteSaveCopy() {
  if (state.noteUnreadable) return "Not editable";
  if (state.noteSaveState === "saving") return "Saving…";
  if (state.noteSaveState === "saved") return "Saved on this Mac";
  return "Stored on this Mac";
}

function permissionAction(permission) {
  if (!permission || permission.probeUnavailable) return { action: "open-settings", label: "Open Settings" };
  if (permission.microphone === "not-determined") return { action: "request-microphone", label: "Allow microphone" };
  if (permission.systemAudio === "unmeasured") return { action: "request-system-audio", label: "Allow system audio" };
  return { action: "open-settings", label: "Open Settings" };
}

function render() {
  const editorFocus = captureEditorFocus();
  const status = statusLabel(state.snapshot, state.permissions);
  const audioReady = canOpenStart(state.snapshot, state.permissions);
  let content;
  if (!invoke) content = renderBrowserNotice();
  else if (!state.snapshot || state.snapshot.startup === "checking") content = renderStartup(true);
  else if (state.snapshot.startup !== "ready") content = renderStartup(false);
  else if (state.snapshot.capture !== "idle") content = renderCapture();
  else if (state.selected) content = renderMeeting();
  else content = renderHome();

  root.innerHTML = `
    <div class="app-shell" data-capture="${escapeHtml(state.snapshot?.capture || "opening")}">
      <header class="topbar" data-tauri-drag-region>
        <button class="brand" type="button" data-action="home" data-tauri-drag-region="false">
          <span>Yawn</span>
        </button>
        <div class="topbar-actions" data-tauri-drag-region="false">
          <div class="topbar-status" aria-label="${escapeHtml(status.label)}">
            <span class="status-dot" data-tone="${escapeHtml(status.tone)}"></span>
            <span>${escapeHtml(status.label)}</span>
          </div>
          ${state.snapshot?.startup === "ready" && state.snapshot?.capture === "idle" ? `
            <button class="button button-quiet" type="button" data-action="meetings">Meetings</button>
            ${audioReady ? `<button class="button button-primary" type="button" data-action="open-start">Record</button>` : ""}
          ` : ""}
          <button class="icon-button" type="button" data-action="settings" aria-label="Open Settings">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8.4a3.6 3.6 0 1 0 0 7.2 3.6 3.6 0 0 0 0-7.2Zm8.3 3.6a6.8 6.8 0 0 0-.1-1l2-1.5-2-3.4-2.4 1a8.2 8.2 0 0 0-1.7-1L15.8 3h-4l-.3 2.1a8.2 8.2 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.5a6.8 6.8 0 0 0 0 2l-2 1.5 2 3.4 2.4-1a8.2 8.2 0 0 0 1.7 1l.3 2.1h4l.3-2.1a8.2 8.2 0 0 0 1.7-1l2.4 1 2-3.4-2-1.5a6.8 6.8 0 0 0 .1-1Z" /></svg>
          </button>
        </div>
      </header>
      <main class="stage">${content}</main>
      ${state.modal === "start" ? renderStartSheet() : ""}
      ${state.modal === "rename-meeting" ? renderRenameMeetingSheet() : ""}
      ${["delete-recording", "delete-transcript", "delete-meeting"].includes(state.modal) ? renderMeetingDeletionSheet() : ""}
      ${state.notice ? `<aside class="toast toast-notice" role="status"><button type="button" data-action="clear-notice" aria-label="Dismiss">×</button>${escapeHtml(state.notice)}</aside>` : ""}
      ${state.error ? `<aside class="toast" role="alert"><button type="button" data-action="clear-error" aria-label="Dismiss">×</button>${escapeHtml(state.error)}</aside>` : ""}
    </div>
  `;
  restoreEditorFocus(editorFocus);
  syncActivityClock();
}

// Snapshot polling keeps recording and transcription honest, but rebuilding the
// whole document used to replace the active textarea every 900 ms. Preserve a
// real editor's focus and selection only when the same meeting still owns it.
function captureEditorFocus() {
  const active = document.activeElement;
  const field = active?.dataset?.field;
  if (!["operator-note", "library-operator-note", "transcript-search"].includes(field)) return null;
  if (!active.dataset.meetingId) return null;
  return {
    field,
    meetingId: active.dataset.meetingId,
    start: Number.isInteger(active.selectionStart) ? active.selectionStart : null,
    end: Number.isInteger(active.selectionEnd) ? active.selectionEnd : null,
    direction: active.selectionDirection || "none",
  };
}

function restoreEditorFocus(focus) {
  if (!focus) return;
  const target = Array.from(root.querySelectorAll(`[data-field="${focus.field}"]`))
    .find((candidate) => candidate.dataset.meetingId === focus.meetingId);
  if (!target || target.disabled) return;
  target.focus({ preventScroll: true });
  if (focus.start === null || focus.end === null || typeof target.setSelectionRange !== "function") return;
  const start = Math.min(focus.start, target.value.length);
  const end = Math.min(Math.max(start, focus.end), target.value.length);
  target.setSelectionRange(start, end, focus.direction);
}

function renderBrowserNotice() {
  return `
    <section class="startup-card attention">
      <div class="startup-orb" aria-hidden="true"></div>
      <p class="eyebrow">Desktop app required</p>
      <h1>Open Yawn from Applications.</h1>
      <p class="browser-note">This page has no access to your microphone, local meetings, or note storage in a browser. Run the desktop app to use Yawn.</p>
    </section>
  `;
}

function renderStartup(checking) {
  const problem = state.snapshot?.error || "Yawn could not complete its local startup check.";
  const progress = state.snapshot?.startup_message || "Yawn is checking its private workspace.";
  return `
    <section class="startup-card ${checking ? "" : "attention"}">
      <div class="startup-orb" aria-hidden="true"></div>
      <p class="eyebrow">${checking ? "Checking your local engine" : "Needs attention"}</p>
      <h1>${checking ? "Getting Yawn ready." : "Yawn cannot record yet."}</h1>
      <p class="lede">${checking ? `${escapeHtml(progress)} Recording stays off until that finishes.` : escapeHtml(problem)}</p>
      ${checking ? "" : `<button class="button button-primary" type="button" data-action="retry-startup">Check again</button>`}
    </section>
  `;
}

function renderHome() {
  const permission = permissionSummary(state.permissions);
  const audioReady = permission.state === "ready";
  const setupAction = permissionAction(state.permissions);
  const library = state.library;
  return `
    <section class="home-workbench" aria-labelledby="home-title">
      <div class="home-copy">
        <p class="eyebrow">New meeting</p>
        <h1 id="home-title">Capture the conversation. Keep your own judgment.</h1>
        <p class="lede">A local recording, your private notes, and a transcript you can check when a detail matters.</p>
      </div>
      <div class="home-action">
        ${audioReady ? `
          <div class="inline-actions">
            <button class="button button-record" type="button" data-action="open-start">Record</button>
            <span class="shortcut" aria-label="Keyboard shortcut">⌘ R</span>
          </div>
          <p>Everything stays on this Mac. No account, bot, or automatic sharing.</p>
        ` : `
          <button class="button button-primary" type="button" data-action="${setupAction.action}">${escapeHtml(setupAction.label)}</button>
          <p><strong>${escapeHtml(permission.title)}</strong><br />${escapeHtml(permission.detail)}</p>
        `}
      </div>
    </section>
    <section aria-labelledby="meetings-heading">
      <div class="section-heading">
        <h2 id="meetings-heading">Recent meetings</h2>
        ${library?.total ? `<input class="search-input" type="search" data-field="library-search" value="${escapeHtml(state.search)}" placeholder="Find a meeting by title" aria-label="Find a meeting by title" />` : ""}
      </div>
      ${renderLibrary(library)}
    </section>
  `;
}

function renderLibrary(library) {
  if (!library) return `<p class="quiet-copy">Loading meetings saved on this Mac…</p>`;
  if (!library.rows?.length) {
    const message = state.search.trim()
      ? library.message || "No meeting matches that title."
      : "Your finished meetings will appear here. Start with the next conversation you want to remember.";
    return `<div class="empty-library"><h3>${state.search.trim() ? "No matching meetings" : "No meetings yet"}</h3><p>${escapeHtml(message)}</p></div>`;
  }
  return `
    <div class="meeting-list" role="list">
      ${library.rows.map((row) => `
        <button class="meeting-row" type="button" role="listitem" data-action="open-meeting" data-handle="${escapeHtml(row.handle)}">
          <span>
            <span class="meeting-row-title">${escapeHtml(row.label || `Meeting · ${dateLabel(row.createdAtEpochSeconds)}`)}</span>
            <span class="meeting-row-meta">${escapeHtml(dateLabel(row.createdAtEpochSeconds))}${row.transcriptAvailable ? " · transcript available" : " · note only"}</span>
          </span>
          <span class="meeting-row-arrow" aria-hidden="true">›</span>
        </button>
      `).join("")}
    </div>
  `;
}

function renderCapture() {
  const snapshot = state.snapshot;
  const presentation = capturePresentation(snapshot);
  const terminal = ["transcript-ready", "transcription-failed", "recovered-interrupted"].includes(snapshot.capture);
  const disabled = state.noteUnreadable || !snapshot.meeting_id;
  const context = snapshot.error || snapshot.warnings?.[0] || "";
  return `
    <section class="session-workspace" aria-labelledby="capture-title">
      <header class="session-toolbar">
        <div class="session-status">
          <span class="record-dot" data-tone="${escapeHtml(presentation.tone)}" aria-hidden="true"></span>
          <div>
            <p class="eyebrow">${escapeHtml(presentation.eyebrow)}</p>
            <h1 id="capture-title">${escapeHtml(presentation.title)}</h1>
            <p>${escapeHtml(presentation.detail)}</p>
          </div>
        </div>
        ${captureAction(snapshot, terminal)}
      </header>
      <div class="capture-facts" aria-label="Recording state">
        <span class="status-pill" data-tone="${escapeHtml(presentation.tone)}">${escapeHtml(humanize(snapshot.capture))}</span>
        ${snapshot.mic_state ? `<span class="fact-pill">Mic: ${escapeHtml(snapshot.mic_state)}</span>` : ""}
        ${snapshot.system_state ? `<span class="fact-pill">System audio: ${escapeHtml(snapshot.system_state)}</span>` : ""}
      </div>
      ${renderActivityMonitor(snapshot)}
      ${context ? `<p class="message-card ${presentation.tone === "attention" ? "attention" : ""}">${escapeHtml(context)}</p>` : ""}
      <article class="note-workbench">
        <div class="note-editor-head"><strong>Your notes</strong><span class="save-state" id="note-save-state">${escapeHtml(noteSaveCopy())}</span></div>
        <textarea class="note-editor" data-field="operator-note" data-meeting-id="${escapeHtml(snapshot.meeting_id || "")}" aria-label="Your meeting notes" placeholder="Write down the detail you will want to verify later." ${disabled ? "disabled" : ""}>${escapeHtml(state.noteDraft)}</textarea>
        <div class="capture-foot">
          <p>${state.noteUnreadable ? "This note could not be read, so Yawn will not overwrite it." : "Saved separately from the transcript. These are your notes, not generated claims."}</p>
        </div>
      </article>
      ${snapshot.turns?.length ? renderTranscript(snapshot.turns, terminal ? "Source transcript" : "Live transcript", terminal ? "The retained record for checking a detail that matters." : "Yawn adds local transcription here as it becomes available.", {
        copyAction: "copy-current-transcript",
        openFileAction: snapshot.capture === "transcript-ready" && snapshot.current_transcript_sha256 ? "open-current-transcript-file" : "",
      }) : ""}
    </section>
  `;
}

function renderActivityMonitor(snapshot) {
  const activity = captureActivity(snapshot);
  if (!activity) return "";
  const startedAt = Number(snapshot.capture_state_started_at_epoch_seconds);
  const elapsed = captureActivityElapsedSeconds(snapshot);
  const heartbeatAt = Number(snapshot.transcription_last_worker_heartbeat_at_epoch_seconds);
  const heartbeatAge = transcriptionWorkerHeartbeatAgeSeconds(snapshot);
  return `
    <section class="activity-monitor" data-tone="${escapeHtml(activity.tone)}" aria-labelledby="activity-title">
      <div>
        <p class="eyebrow">Activity</p>
        <h2 id="activity-title">${escapeHtml(activity.label)}</h2>
        <p>${escapeHtml(activity.detail)}</p>
      </div>
      <div class="activity-timing">
        <strong data-activity-elapsed data-activity-started-at="${Number.isFinite(startedAt) ? startedAt : ""}">${elapsed === null ? "Working" : timeLabel(elapsed)}</strong>
        <span>elapsed in this step</span>
        ${snapshot.capture === "transcribing" ? `<span class="activity-heartbeat" data-transcription-heartbeat data-transcription-heartbeat-at="${Number.isFinite(heartbeatAt) ? heartbeatAt : ""}" aria-live="polite">${heartbeatAge === null ? "Waiting for a local-worker confirmation" : `Last confirmed by local worker ${elapsedAgoLabel(heartbeatAge)}`}</span>` : ""}
      </div>
    </section>
  `;
}

function updateActivityClock() {
  for (const target of document.querySelectorAll("[data-activity-elapsed]")) {
    const rawStartedAt = target.dataset.activityStartedAt;
    if (!rawStartedAt) continue;
    const startedAt = Number(rawStartedAt);
    if (!Number.isFinite(startedAt)) continue;
    target.textContent = timeLabel(Math.max(0, Math.floor(Date.now() / 1000 - startedAt)));
  }
  for (const target of document.querySelectorAll("[data-transcription-heartbeat]")) {
    const rawHeartbeatAt = target.dataset.transcriptionHeartbeatAt;
    if (!rawHeartbeatAt) continue;
    const heartbeatAt = Number(rawHeartbeatAt);
    if (!Number.isFinite(heartbeatAt)) continue;
    target.textContent = `Last confirmed by local worker ${elapsedAgoLabel(Date.now() / 1000 - heartbeatAt)}`;
  }
}

function syncActivityClock() {
  if (!captureActivity(state.snapshot)) {
    clearInterval(activityTimer);
    activityTimer = undefined;
    return;
  }
  updateActivityClock();
  if (activityTimer === undefined) activityTimer = setInterval(updateActivityClock, 1000);
}

function captureAction(snapshot, terminal) {
  if (snapshot.capture === "recording") {
    return `<button class="button button-record" type="button" data-action="stop-recording" ${state.busyAction === "stop" ? "disabled" : ""}>${state.busyAction === "stop" ? "Stopping…" : "Stop recording"}</button>`;
  }
  if (terminal) {
    const leaving = ["dismiss", "record-another"].includes(state.busyAction);
    if (snapshot.capture === "transcript-ready") {
      return `<div class="inline-actions" aria-label="Meeting actions">
        <button class="button button-quiet" type="button" data-action="dismiss-current" ${leaving ? "disabled" : ""}>${state.busyAction === "dismiss" ? "Opening Meetings…" : "Back to Meetings"}</button>
        <button class="button button-primary" type="button" data-action="record-another" ${leaving ? "disabled" : ""}>${state.busyAction === "record-another" ? "Preparing…" : "Record another meeting"}</button>
      </div>`;
    }
    return `<button class="button button-primary" type="button" data-action="dismiss-current" ${leaving ? "disabled" : ""}>${state.busyAction === "dismiss" ? "Opening Meetings…" : "Back to Meetings"}</button>`;
  }
  return "";
}

function transcriptActionStatus(scope) {
  return state.transcriptActionStatus?.[scope] || "";
}

function renderTranscript(turns, title, detail = "", { copyAction = "", openFileAction = "", workspace = false } = {}) {
  const scope = copyAction.includes("library") ? "library" : "current";
  const copyBusy = state.busyAction === copyAction;
  const fileBusy = state.busyAction === openFileAction;
  const query = workspace ? state.transcriptQuery.trim() : "";
  const visibleTurns = workspace ? transcriptTurnsMatching(turns, query) : turns;
  const actions = copyAction || openFileAction ? `<div class="transcript-actions" aria-label="Transcript actions">
    ${copyAction ? `<button class="button button-quiet button-small" type="button" data-action="${copyAction}" ${copyBusy ? "disabled" : ""}>${copyBusy ? "Copying…" : "Copy transcript"}</button>` : ""}
    ${openFileAction ? `<button class="button button-quiet button-small" type="button" data-action="${openFileAction}" ${fileBusy ? "disabled" : ""}>${fileBusy ? "Opening…" : "Open transcript file"}</button>` : ""}
    <span class="transcript-action-status" role="status" aria-live="polite">${escapeHtml(transcriptActionStatus(scope))}</span>
  </div>` : "";
  const transcriptLines = visibleTurns.map((turn) => `
    <div class="transcript-line ${turn.withheld ? "withheld" : ""}">
      <time>${escapeHtml(timeLabel(turn.start))}</time>
      <p>${turn.withheld ? "This turn was withheld by the voice check." : escapeHtml(turn.text)}</p>
    </div>
  `).join("");
  if (workspace) {
    const queryStatus = query
      ? visibleTurns.length
        ? `${visibleTurns.length} matching ${visibleTurns.length === 1 ? "moment" : "moments"}.`
        : "No matching moments."
      : "Find a phrase, decision, or follow-up.";
    return `
      <section class="transcript-panel transcript-workspace" aria-labelledby="transcript-heading">
        <div class="transcript-workspace-toolbar">
          <div class="transcript-heading"><h3 id="transcript-heading">${escapeHtml(title)}</h3>${detail ? `<p>${escapeHtml(detail)}</p>` : ""}</div>
          ${actions}
        </div>
        <div class="transcript-search-row">
          <label class="screen-reader-only" for="transcript-search-input">Find in transcript</label>
          <input class="transcript-search" id="transcript-search-input" data-field="transcript-search" data-meeting-id="${escapeHtml(state.selected?.row?.meetingId || "")}" type="search" value="${escapeHtml(state.transcriptQuery)}" placeholder="Find in transcript" autocomplete="off" aria-describedby="transcript-search-status">
          ${query ? `<button class="button button-quiet button-small" type="button" data-action="clear-transcript-search">Clear</button>` : ""}
          <span class="transcript-search-status" id="transcript-search-status" role="status" aria-live="polite">${escapeHtml(queryStatus)}</span>
        </div>
        <div class="transcript-scroll" tabindex="0" aria-label="Transcript turns">
          ${transcriptLines || `<p class="transcript-empty">${query ? "No retained transcript turn matches that search." : "No transcript turns are available."}</p>`}
        </div>
      </section>
    `;
  }
  return `
    <section class="transcript-panel" aria-labelledby="transcript-heading">
      <div class="transcript-heading"><h3 id="transcript-heading">${escapeHtml(title)}</h3>${detail ? `<p>${escapeHtml(detail)}</p>` : ""}</div>
      ${actions}
      ${transcriptLines}
    </section>
  `;
}

function renderDraftPoints(claims, claimEvidence) {
  if (!claims.length) return "";
  return `
    <details class="draft-points" open>
      <summary><span><strong>Draft from transcript</strong><small>Generated points need review against the retained source.</small></span><span class="draft-points-state">Review</span></summary>
      <div class="draft-points-content">
        <ul class="claim-list">${claims.map((claim) => `<li class="claim-item">
          <span class="claim-label">${escapeHtml(humanize(claim.claimType))}</span>
          <p>${escapeHtml(claim.claim)}</p>
          ${renderClaimEvidence(claim, claimEvidence[claim.ordinal])}
        </li>`).join("")}</ul>
      </div>
    </details>
  `;
}

function renderMeeting() {
  const { row, note, transcript } = state.selected;
  const title = row.label || `Meeting · ${dateLabel(row.createdAtEpochSeconds)}`;
  const claims = note?.claims || [];
  const operatorNote = note?.operatorNote;
  const selectedNoteState = state.selected?.operatorNoteSaveState || "local";
  const selectedNoteCopy = operatorNote?.unreadable
    ? "Not editable"
    : selectedNoteState === "saving"
      ? "Saving…"
      : selectedNoteState === "saved"
        ? "Saved on this Mac"
        : "Stored on this Mac";
  const noteEditable = !operatorNote?.unreadable && Boolean(note?.operatorNoteHandle);
  const claimEvidence = state.selected.claimEvidence || {};
  const metadataRevision = state.library?.metadataRevision;
  const canRename = metadataRevision != null && Number.isInteger(Number(metadataRevision));
  const canDeleteRecording = Boolean(note?.audioDeletionHandle);
  const canDeleteTranscript = Boolean(note?.transcriptDeletionHandle);
  const canDeleteMeeting = Boolean(note?.meetingDeletionHandle);
  const canManage = canDeleteRecording || canDeleteTranscript || canDeleteMeeting;
  const retentionMessage = note?.audioRetention?.message || "Audio-retention details are unavailable for this meeting.";
  return `
    <article class="meeting-page meeting-workspace-page" aria-labelledby="meeting-title">
      <button class="text-button" type="button" data-action="meetings">Back to meetings</button>
      <header class="meeting-detail-header">
        <p class="eyebrow">Saved on this Mac</p>
        <div class="meeting-title-row">
          <h1 class="meeting-title" id="meeting-title">${escapeHtml(title)}</h1>
          <div class="meeting-header-actions">
            ${canRename ? `<button class="button button-quiet button-small" type="button" data-action="rename-meeting">Rename</button>` : ""}
            ${canManage ? `<div class="meeting-manage-control">
              <button class="button button-secondary button-small" type="button" data-action="toggle-meeting-management" aria-expanded="${state.meetingManagementOpen ? "true" : "false"}" aria-controls="meeting-manage-menu">Manage</button>
              ${state.meetingManagementOpen ? `<div class="meeting-manage-menu" id="meeting-manage-menu" role="group" aria-label="Manage this meeting">
                <p>These actions affect only this meeting on this Mac.</p>
                ${canDeleteRecording ? `<button class="button button-secondary button-small" type="button" data-action="delete-recording">Delete recording</button>` : ""}
                ${canDeleteTranscript ? `<button class="button button-secondary button-small" type="button" data-action="delete-transcript">Delete transcript</button>` : ""}
                ${canDeleteMeeting ? `<button class="button button-danger button-small" type="button" data-action="delete-meeting">Delete meeting…</button>` : ""}
              </div>` : ""}
            </div>` : ""}
          </div>
        </div>
        <div class="meeting-meta"><span>${escapeHtml(dateLabel(row.createdAtEpochSeconds))}</span><span>${escapeHtml(note?.state ? humanize(note.state) : "Loading note")}</span></div>
        <p class="meeting-storage-note">${escapeHtml(retentionMessage)}</p>
      </header>
      ${note?.message && !claims.length ? `<p class="message-card ${note.state === "summary-failed" ? "attention" : ""}">${escapeHtml(note.message)}</p>` : ""}
      <div class="meeting-workspace">
        <main class="meeting-source-pane">
          ${renderDraftPoints(claims, claimEvidence)}
          ${transcript?.turns?.length ? renderTranscript(transcript.turns, "Source transcript", "The retained record for checking a decision, owner, or follow-up.", {
            copyAction: "copy-library-transcript",
            openFileAction: "open-library-transcript-file",
            workspace: true,
          }) : transcript?.message ? `<section class="note-section transcript-unavailable"><p class="message-card">${escapeHtml(transcript.message)}</p></section>` : ""}
        </main>
        <aside class="meeting-notes-pane">
          <section class="note-section your-notes-section" aria-labelledby="operator-note-heading">
          <div class="note-editor-head"><h3 id="operator-note-heading">Your notes</h3><span class="save-state" id="library-note-save-state">${escapeHtml(selectedNoteCopy)}</span></div>
          ${operatorNote?.unreadable
            ? `<p class="message-card attention">Yawn could not read this meeting’s personal note, so it was left unchanged.</p>`
            : `<textarea class="note-editor meeting-notes-editor" data-field="library-operator-note" data-meeting-id="${escapeHtml(row.meetingId || "")}" aria-label="Your meeting notes" placeholder="Write down the detail you will want to verify later." ${noteEditable ? "" : "disabled"}>${escapeHtml(state.selected?.operatorNoteDraft || "")}</textarea>
              <p class="note-editor-help">${noteEditable ? "Saved separately from the transcript. These are your notes, not generated claims." : "Reopen this meeting to edit its notes."}</p>`}
          </section>
        </aside>
      </div>
    </article>
  `;
}

function renderClaimEvidence(claim, evidence) {
  if (!claim.locatorCount) return `<span class="claim-source-unavailable">No source passage is available for this point.</span>`;
  if (evidence?.state === "evidence" && evidence.text) {
    return `
      <div class="claim-evidence">
        <span>Transcript source · ${escapeHtml(timeLabel(evidence.start))}</span>
        <p>${escapeHtml(evidence.text)}</p>
      </div>
    `;
  }
  const action = `evidence-${claim.ordinal}`;
  return `<button class="claim-source-button" type="button" data-action="open-claim-evidence" data-ordinal="${escapeHtml(claim.ordinal)}" ${state.busyAction === action ? "disabled" : ""}>${state.busyAction === action ? "Opening source…" : "Show source"}</button>`;
}

function renderStartSheet() {
  const permission = permissionSummary(state.permissions);
  const audioReady = permission.state === "ready";
  const allConfirmed = Object.values(state.consent).every(Boolean);
  const action = permissionAction(state.permissions);
  return `
    <div class="modal-backdrop" role="presentation">
      <section class="start-sheet" role="dialog" aria-modal="true" aria-labelledby="start-sheet-title">
        <div class="sheet-head">
          <div><p class="eyebrow">Before recording</p><h2 id="start-sheet-title">Make the start explicit.</h2><p>Yawn records only after you confirm the meeting is ready to capture.</p></div>
          <button class="icon-button" type="button" data-action="close-start" aria-label="Close">×</button>
        </div>
        ${audioReady ? "" : `<div class="message-card attention"><strong>${escapeHtml(permission.title)}</strong><p>${escapeHtml(permission.detail)}</p><button class="text-button" type="button" data-action="${action.action}">${escapeHtml(action.label)}</button></div>`}
        <label class="field-label">Keep recording audio for
          <small>Your transcript and notes stay local. This choice covers the saved audio.</small>
          <select class="select" data-field="retention-days">${[1, 7, 30].map((days) => `<option value="${days}" ${Number(state.retentionDays) === days ? "selected" : ""}>${retentionLabel(days)}</option>`).join("")}</select>
        </label>
        <div class="attestation-list">
          ${attestation("participantsConsented", "Everyone in this meeting has agreed to be recorded.")}
          ${attestation("headphones", "I am using headphones for this recording.")}
          ${attestation("operatorAlone", "I am the only person near this microphone.")}
        </div>
        <div class="sheet-actions">
          <button class="button button-quiet" type="button" data-action="close-start">Cancel</button>
          <button class="button button-record" type="button" data-action="start-recording" ${!audioReady || !allConfirmed || state.busyAction === "start" ? "disabled" : ""}>${state.busyAction === "start" ? "Starting…" : "Start recording"}</button>
        </div>
      </section>
    </div>
  `;
}

function renderRenameMeetingSheet() {
  const selection = state.selected;
  if (!selection) return "";
  const saving = state.busyAction === "rename-meeting";
  return `
    <div class="modal-backdrop" role="presentation">
      <section class="start-sheet" role="dialog" aria-modal="true" aria-labelledby="rename-meeting-title">
        <div class="sheet-head">
          <div><p class="eyebrow">Meeting name</p><h2 id="rename-meeting-title">Give this meeting a useful name.</h2><p>Only this local meeting’s label changes. The recording, transcript, and notes stay as they are.</p></div>
          <button class="icon-button" type="button" data-action="close-modal" aria-label="Close">×</button>
        </div>
        <form data-form="rename-meeting">
          <label class="field-label" for="meeting-title-input">Meeting name
            <input class="meeting-title-input" id="meeting-title-input" data-field="meeting-title" maxlength="120" value="${escapeHtml(state.renameDraft)}" placeholder="e.g. Q3 pricing review" autocomplete="off" />
            <small>Leave this empty to use the opening line from the transcript again.</small>
          </label>
          <div class="sheet-actions">
            <button class="button button-quiet" type="button" data-action="close-modal">Cancel</button>
            <button class="button button-primary" type="submit" ${saving ? "disabled" : ""}>${saving ? "Saving…" : "Save name"}</button>
          </div>
        </form>
      </section>
    </div>
  `;
}

function renderMeetingDeletionSheet() {
  const selection = state.selected;
  if (!selection) return "";
  const deleteRecording = state.modal === "delete-recording";
  const deleteTranscript = state.modal === "delete-transcript";
  const action = deleteRecording
    ? "confirm-delete-recording"
    : deleteTranscript
      ? "confirm-delete-transcript"
      : "confirm-delete-meeting";
  const busy = state.busyAction === action;
  const title = selection.row.label || `Meeting · ${dateLabel(selection.row.createdAtEpochSeconds)}`;
  const heading = deleteRecording
    ? "Delete this recording?"
    : deleteTranscript
      ? "Delete this transcript?"
      : "Delete this meeting?";
  const detail = deleteRecording
    ? "This permanently removes the saved microphone and system audio from this Mac. The transcript and your personal notes stay."
    : deleteTranscript
      ? "This permanently removes the transcript and generated points from this Mac. Any recording and your personal notes stay."
      : "This permanently removes the recording, transcript, generated points, personal notes, and saved name from this Mac.";
  const label = deleteRecording ? "Delete recording" : deleteTranscript ? "Delete transcript" : "Delete meeting";
  return `
    <div class="modal-backdrop" role="presentation">
      <section class="start-sheet destructive-sheet" role="dialog" aria-modal="true" aria-labelledby="delete-meeting-title">
        <div class="sheet-head">
          <div><p class="eyebrow">Permanent deletion</p><h2 id="delete-meeting-title">${heading}</h2><p>${escapeHtml(detail)}</p></div>
          <button class="icon-button" type="button" data-action="close-modal" aria-label="Close">×</button>
        </div>
        <p class="destructive-target">${escapeHtml(title)}</p>
        <div class="sheet-actions">
          <button class="button button-quiet" type="button" data-action="close-modal">Cancel</button>
          <button class="button button-danger" type="button" data-action="${action}" ${busy ? "disabled" : ""}>${busy ? "Deleting…" : label}</button>
        </div>
      </section>
    </div>
  `;
}

function attestation(name, label) {
  return `<label class="check-row"><input type="checkbox" data-field="attestation" data-attestation="${name}" ${state.consent[name] ? "checked" : ""} /><span>${escapeHtml(label)}</span></label>`;
}

function setNoteSaveCopy() {
  const target = document.querySelector("#note-save-state");
  if (target) target.textContent = noteSaveCopy();
}

function setLibraryNoteSaveCopy() {
  const selection = state.selected;
  const target = document.querySelector("#library-note-save-state");
  if (!selection || !target) return;
  const unreadable = selection.note?.operatorNote?.unreadable;
  target.textContent = unreadable
    ? "Not editable"
    : selection.operatorNoteSaveState === "saving"
      ? "Saving…"
      : selection.operatorNoteSaveState === "saved"
        ? "Saved on this Mac"
        : "Stored on this Mac";
}

function reportError(error) {
  state.error = String(error instanceof Error ? error.message : error).replace(/^Error:\s*/, "").trim() || "Yawn could not complete that action.";
  render();
}

function clearCurrentNote() {
  clearTimeout(noteSaveTimer);
  noteSaveTimer = undefined;
  state.noteDraft = "";
  state.noteLoadedFor = "";
  state.noteSaveState = "local";
  state.noteUnreadable = false;
  state.transcriptActionStatus = { ...state.transcriptActionStatus, current: "" };
}

function canReadCurrentNote(snapshot) {
  return ["recording", "stopping", "captured", "transcribing", "transcript-ready", "transcription-failed", "recovered-interrupted"].includes(snapshot?.capture);
}

async function refreshSnapshot({ shouldRender = true } = {}) {
  const oldMeetingId = state.snapshot?.meeting_id;
  state.snapshot = await invoke("app_snapshot");
  const meetingId = state.snapshot.meeting_id;
  if (!meetingId && oldMeetingId) clearCurrentNote();
  if (meetingId && meetingId !== state.noteLoadedFor && canReadCurrentNote(state.snapshot)) void loadCurrentNote(meetingId);
  if (state.snapshot.capture === "idle" && state.activeView === "capture") state.activeView = "home";
  if (shouldRender) render();
}

async function loadCurrentNote(meetingId) {
  if (state.noteLoading || state.noteLoadedFor === meetingId || state.noteDraft) return;
  state.noteLoading = true;
  try {
    const note = await invoke("operator_note");
    if (state.snapshot?.meeting_id !== meetingId || state.noteDraft) return;
    state.noteLoadedFor = meetingId;
    state.noteDraft = note.text || "";
    state.noteUnreadable = note.unreadable === true;
    state.noteSaveState = note.unreadable ? "unreadable" : note.text ? "saved" : "local";
    render();
  } catch {
    // The meeting directory can briefly be unavailable while capture arms.
  } finally {
    state.noteLoading = false;
  }
}

async function refreshLibrary() {
  const title = state.search.trim();
  state.library = await invoke("library_snapshot", { filter: title ? { title } : null });
}

async function refreshPermissions() {
  if (permissionsRefreshTask) return permissionsRefreshTask;
  permissionsRefreshTask = (async () => {
    state.permissions = mergePermissions(state.permissions, await invoke("first_run_permissions"));
  })();
  try {
    await permissionsRefreshTask;
  } finally {
    permissionsRefreshTask = undefined;
  }
}

function refreshPermissionsOnReturn() {
  if (!invoke) return;
  void refreshPermissions()
    .then(render)
    .catch(reportError);
}

async function runBusy(action, operation) {
  state.busyAction = action;
  render();
  try {
    await operation();
  } catch (error) {
    reportError(error);
  } finally {
    state.busyAction = "";
    render();
  }
}

async function requestPermission(kind) {
  const command = kind === "microphone" ? "first_run_request_microphone" : "first_run_request_system_audio";
  await runBusy("permission", async () => {
    state.permissions = mergePermissions(state.permissions, await invoke(command));
  });
}

function openStart() {
  if (!canOpenStart(state.snapshot, state.permissions)) return;
  state.modal = "start";
  render();
}

async function startRecording() {
  if (!canOpenStart(state.snapshot, state.permissions) || !Object.values(state.consent).every(Boolean)) return;
  await runBusy("start", async () => {
    state.snapshot = await invoke("start_meeting", {
      retentionDays: Number(state.retentionDays),
      attestation: state.consent,
    });
    clearCurrentNote();
    state.activeView = "capture";
    state.modal = "";
    state.selected = null;
  });
}

async function stopRecording() {
  if (state.snapshot?.capture !== "recording") return;
  await runBusy("stop", async () => {
    state.snapshot = await invoke("stop_meeting");
    state.activeView = "capture";
  });
}

async function dismissCurrent() {
  await leaveCurrentCapture();
}

async function recordAnother() {
  await leaveCurrentCapture({ startAnother: true });
}

async function leaveCurrentCapture({ startAnother = false } = {}) {
  await runBusy(startAnother ? "record-another" : "dismiss", async () => {
    await flushPendingNoteSave();
    state.snapshot = await invoke("dismiss_meeting");
    clearCurrentNote();
    state.activeView = "home";
    state.selected = null;
    await refreshLibrary();
    if (startAnother && canOpenStart(state.snapshot, state.permissions)) state.modal = "start";
  });
}

async function openMeeting(handle) {
  const row = state.library?.rows?.find((candidate) => candidate.handle === handle);
  if (!row) return;
  await flushSelectedNoteSave();
  await runBusy("meeting", async () => {
    await loadSelectedMeeting(row);
  });
}

async function loadSelectedMeeting(row) {
  state.transcriptActionStatus = { ...state.transcriptActionStatus, library: "" };
  const note = await invoke("library_open_note", { handle: row.handle });
  const transcript = note.transcriptHandle
    ? await invoke("library_open_transcript", { handle: note.transcriptHandle })
    : null;
  const operatorNote = note.operatorNote || { text: "", unreadable: false };
  state.meetingManagementOpen = false;
  state.transcriptQuery = "";
  state.selected = {
    row,
    note,
    transcript,
    claimEvidence: {},
    operatorNoteDraft: operatorNote.text || "",
    operatorNoteSaveQueue: Promise.resolve(),
    operatorNoteSaveState: operatorNote.unreadable ? "unreadable" : operatorNote.text ? "saved" : "local",
  };
  state.activeView = "meeting";
}

async function reopenSelectedMeeting(meetingId) {
  await refreshLibrary();
  const row = state.library?.rows?.find((candidate) => candidate.meetingId === meetingId);
  if (!row) {
    state.selected = null;
    state.activeView = "home";
    return;
  }
  await loadSelectedMeeting(row);
}

function openMeetingRename() {
  const selection = state.selected;
  if (!selection) return;
  state.meetingManagementOpen = false;
  state.renameDraft = selection.row.labelSource === "operator" ? selection.row.label || "" : "";
  state.modal = "rename-meeting";
  render();
  queueMicrotask(() => root.querySelector("#meeting-title-input")?.focus());
}

async function saveMeetingTitle() {
  const selection = state.selected;
  const metadataRevision = state.library?.metadataRevision;
  const revision = Number(metadataRevision);
  if (!selection?.row?.meetingId || metadataRevision == null || !Number.isInteger(revision)) {
    reportError(new Error("Reopen Meetings before changing this name."));
    return;
  }
  await flushSelectedNoteSave();
  await runBusy("rename-meeting", async () => {
    const title = state.renameDraft.trim();
    const response = await invoke("library_set_meeting_title", {
      expectedRevision: revision,
      meetingId: selection.row.meetingId,
      title: title || null,
    });
    if (response.state !== "ok") throw new Error(response.message || "Yawn could not change this meeting name.");
    if (state.selected !== selection) return;
    state.modal = "";
    state.notice = title ? "Meeting name saved on this Mac." : "Meeting name reset to its opening line.";
    await reopenSelectedMeeting(selection.row.meetingId);
  });
}

function openMeetingDeletion(kind) {
  const selection = state.selected;
  if (!selection) return;
  const allowed = kind === "delete-recording"
    ? Boolean(selection.note?.audioDeletionHandle)
    : kind === "delete-transcript"
      ? Boolean(selection.note?.transcriptDeletionHandle)
      : Boolean(selection.note?.meetingDeletionHandle);
  if (!allowed) return;
  state.meetingManagementOpen = false;
  state.modal = kind;
  render();
}

async function deleteSelectedRecording() {
  const selection = state.selected;
  const handle = selection?.note?.audioDeletionHandle;
  if (!selection?.row?.meetingId || !handle) {
    reportError(new Error("Reopen this meeting before deleting its recording."));
    return;
  }
  await flushSelectedNoteSave();
  await runBusy("confirm-delete-recording", async () => {
    const response = await invoke("preview_delete_meeting_audio", { handle });
    if (!["released", "already-released"].includes(response.state)) {
      throw new Error(response.message || "Yawn could not delete this recording.");
    }
    if (state.selected !== selection) return;
    state.modal = "";
    state.notice = response.message || "The recording was permanently deleted from this Mac.";
    await reopenSelectedMeeting(selection.row.meetingId);
  });
}

async function deleteSelectedTranscript() {
  const selection = state.selected;
  const handle = selection?.note?.transcriptDeletionHandle;
  if (!selection?.row?.meetingId || !handle) {
    reportError(new Error("Reopen this meeting before deleting its transcript."));
    return;
  }
  await flushSelectedNoteSave();
  await runBusy("confirm-delete-transcript", async () => {
    const response = await invoke("preview_delete_meeting_transcript", { handle, confirmed: true });
    if (!["removed", "already-removed"].includes(response.state)) {
      throw new Error(response.message || "Yawn could not delete this transcript.");
    }
    if (state.selected !== selection) return;
    state.modal = "";
    state.notice = response.message || "The transcript and generated notes were permanently deleted from this Mac.";
    await reopenSelectedMeeting(selection.row.meetingId);
  });
}

async function deleteSelectedMeeting() {
  const selection = state.selected;
  const handle = selection?.note?.meetingDeletionHandle;
  if (!handle) {
    reportError(new Error("Reopen this meeting before deleting it."));
    return;
  }
  await flushSelectedNoteSave();
  await runBusy("confirm-delete-meeting", async () => {
    const response = await invoke("preview_delete_meeting", { handle, confirmed: true });
    if (!["removed", "already-removed"].includes(response.state)) {
      throw new Error(response.message || "Yawn could not delete this meeting.");
    }
    if (state.selected !== selection) return;
    state.selected = null;
    state.activeView = "home";
    state.modal = "";
    state.notice = response.message || "The meeting was permanently deleted from this Mac.";
    await refreshLibrary();
  });
}

async function openClaimEvidence(ordinal) {
  const selection = state.selected;
  if (!selection?.row?.meetingId || !Number.isFinite(ordinal)) return;
  await flushSelectedNoteSave();
  await runBusy(`evidence-${ordinal}`, async () => {
    // Claim handles are deliberately one-use capabilities. A fresh local
    // meeting handle keeps every source request scoped to the meeting the
    // operator already opened instead of keeping broad transcript access alive
    // in UI state.
    const library = await invoke("library_snapshot", { filter: null });
    const row = library.rows?.find((candidate) => candidate.meetingId === selection.row.meetingId);
    if (!row?.handle) {
      throw new Error("Yawn could not reopen this retained meeting.");
    }
    const note = await invoke("library_open_note", { handle: row.handle });
    const claim = note.claims?.find((candidate) => Number(candidate.ordinal) === ordinal);
    if (!claim?.handle || !claim.locatorCount) {
      throw new Error("Yawn could not open a retained source passage for this point.");
    }
    const evidence = await invoke("preview_library_open_evidence", {
      handle: claim.handle,
      locatorOrdinal: 0,
    });
    if (evidence.state !== "evidence" || !evidence.text) {
      throw new Error(evidence.message || "Yawn could not open that source passage.");
    }
    if (state.selected?.row?.handle !== selection.row.handle) return;
    state.selected = {
      ...state.selected,
      note,
      transcript: state.selected.transcript && evidence.transcriptHandle
        ? { ...state.selected.transcript, transcriptFileHandle: evidence.transcriptHandle }
        : state.selected.transcript,
      claimEvidence: {
        ...(state.selected.claimEvidence || {}),
        [ordinal]: evidence,
      },
    };
  });
}

function queueNoteSave(text = state.noteDraft, meetingId = state.snapshot?.meeting_id) {
  if (!meetingId || state.noteUnreadable) return Promise.resolve();
  state.noteSaveQueue = state.noteSaveQueue.catch(() => undefined).then(async () => {
    if (state.snapshot?.meeting_id !== meetingId) return;
    state.noteSaveState = "saving";
    setNoteSaveCopy();
    const saved = await invoke("save_operator_note", { text });
    if (state.snapshot?.meeting_id === meetingId && state.noteDraft === text) {
      state.noteUnreadable = saved.unreadable === true;
      state.noteSaveState = saved.unreadable ? "unreadable" : "saved";
      setNoteSaveCopy();
    }
  }).catch((error) => {
    state.noteSaveState = "local";
    state.error = String(error).replace(/^Error:\s*/, "") || "Yawn could not save this note.";
    render();
  });
  return state.noteSaveQueue;
}

function scheduleNoteSave() {
  clearTimeout(noteSaveTimer);
  noteSaveTimer = setTimeout(() => {
    noteSaveTimer = undefined;
    void queueNoteSave();
  }, 600);
}

function queueSelectedNoteSave(text = state.selected?.operatorNoteDraft, selection = state.selected) {
  if (!selection?.row?.meetingId || selection.note?.operatorNote?.unreadable) return Promise.resolve();
  selection.operatorNoteSaveQueue = (selection.operatorNoteSaveQueue || Promise.resolve())
    .catch(() => undefined)
    .then(async () => {
      if (state.selected !== selection) return;
      const handle = selection.note?.operatorNoteHandle;
      if (!handle) throw new Error("Reopen this meeting before saving its notes.");
      selection.operatorNoteSaveState = "saving";
      setLibraryNoteSaveCopy();
      const saved = await invoke("library_save_operator_note", { handle, text });
      if (state.selected !== selection) return;
      selection.note = {
        ...selection.note,
        operatorNote: saved.operatorNote,
        operatorNoteHandle: saved.operatorNoteHandle,
      };
      selection.operatorNoteSaveState = selection.operatorNoteDraft === text ? "saved" : "local";
      setLibraryNoteSaveCopy();
    })
    .catch((error) => {
      if (state.selected !== selection) return;
      selection.operatorNoteSaveState = "local";
      state.error = String(error).replace(/^Error:\s*/, "") || "Yawn could not save this note.";
      render();
    });
  return selection.operatorNoteSaveQueue;
}

function scheduleSelectedNoteSave() {
  clearTimeout(libraryNoteSaveTimer);
  libraryNoteSaveTimer = setTimeout(() => {
    libraryNoteSaveTimer = undefined;
    void queueSelectedNoteSave();
  }, 600);
}

async function flushPendingNoteSave() {
  if (noteSaveTimer !== undefined) {
    clearTimeout(noteSaveTimer);
    noteSaveTimer = undefined;
    await queueNoteSave();
  }
  await state.noteSaveQueue;
}

async function flushSelectedNoteSave() {
  const selection = state.selected;
  if (!selection) return;
  if (libraryNoteSaveTimer !== undefined) {
    clearTimeout(libraryNoteSaveTimer);
    libraryNoteSaveTimer = undefined;
    await queueSelectedNoteSave(selection.operatorNoteDraft, selection);
  }
  await selection.operatorNoteSaveQueue;
}

async function openMeetings() {
  await flushSelectedNoteSave();
  state.selected = null;
  state.meetingManagementOpen = false;
  state.transcriptQuery = "";
  state.activeView = "home";
  if (!invoke) {
    render();
    return;
  }
  await runBusy("library", refreshLibrary);
}

function transcriptTurns(scope) {
  return scope === "library"
    ? state.selected?.transcript?.turns || []
    : state.snapshot?.turns || [];
}

async function writeTranscriptToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const fallback = document.createElement("textarea");
  fallback.value = text;
  fallback.setAttribute("readonly", "");
  fallback.style.cssText = "position:fixed;opacity:0;pointer-events:none;";
  document.body.append(fallback);
  fallback.select();
  const copied = document.execCommand("copy");
  fallback.remove();
  if (!copied) throw new Error("Copy failed. Select the transcript instead.");
}

async function copyTranscript(scope) {
  const text = transcriptPlainText(transcriptTurns(scope));
  if (!text) {
    state.transcriptActionStatus = { ...(state.transcriptActionStatus || {}), [scope]: "Nothing to copy." };
    render();
    return;
  }
  state.transcriptActionStatus = { ...(state.transcriptActionStatus || {}), [scope]: "Copying…" };
  render();
  try {
    await writeTranscriptToClipboard(text);
    state.transcriptActionStatus = { ...(state.transcriptActionStatus || {}), [scope]: "Copied." };
  } catch {
    state.transcriptActionStatus = { ...(state.transcriptActionStatus || {}), [scope]: "Copy failed. Select the transcript instead." };
  }
  render();
}

async function openTranscriptFile(scope) {
  if (scope === "library") await flushSelectedNoteSave();
  await runBusy(`open-${scope}-transcript-file`, async () => {
    if (scope === "current") {
      await invoke("open_current_transcript_file");
      return;
    }
    const selection = state.selected;
    const handle = selection?.transcript?.transcriptFileHandle;
    if (!handle) throw new Error("Reopen this meeting before opening its transcript file.");
    const opened = await invoke("library_open_transcript_file", { handle });
    if (state.selected !== selection || !selection.transcript) return;
    selection.transcript = {
      ...selection.transcript,
      transcriptFileHandle: opened.transcriptFileHandle,
    };
  });
}

async function retryStartup() {
  await runBusy("retry", async () => {
    state.snapshot = await invoke("retry_startup");
    await refreshPermissions();
  });
}

function handleClick(event) {
  const control = event.target.closest("[data-action]");
  if (!control || control.disabled) return;
  const action = control.dataset.action;
  if (action === "home" || action === "meetings") void openMeetings();
  else if (action === "open-start") openStart();
  else if (action === "close-start" || action === "close-modal") { state.modal = ""; render(); }
  else if (action === "start-recording") void startRecording();
  else if (action === "stop-recording") void stopRecording();
  else if (action === "dismiss-current") void dismissCurrent();
  else if (action === "record-another") void recordAnother();
  else if (action === "open-meeting") void openMeeting(control.dataset.handle);
  else if (action === "open-claim-evidence") void openClaimEvidence(Number(control.dataset.ordinal));
  else if (action === "toggle-meeting-management") {
    state.meetingManagementOpen = !state.meetingManagementOpen;
    render();
  }
  else if (action === "rename-meeting") openMeetingRename();
  else if (action === "delete-recording") openMeetingDeletion("delete-recording");
  else if (action === "delete-transcript") openMeetingDeletion("delete-transcript");
  else if (action === "delete-meeting") openMeetingDeletion("delete-meeting");
  else if (action === "confirm-delete-recording") void deleteSelectedRecording();
  else if (action === "confirm-delete-transcript") void deleteSelectedTranscript();
  else if (action === "confirm-delete-meeting") void deleteSelectedMeeting();
  else if (action === "copy-current-transcript") void copyTranscript("current");
  else if (action === "copy-library-transcript") void copyTranscript("library");
  else if (action === "open-current-transcript-file") void openTranscriptFile("current");
  else if (action === "open-library-transcript-file") void openTranscriptFile("library");
  else if (action === "clear-transcript-search") {
    state.transcriptQuery = "";
    render();
    queueMicrotask(() => root.querySelector("[data-field='transcript-search']")?.focus());
  }
  else if (action === "retry-startup") void retryStartup();
  else if (action === "request-microphone") void requestPermission("microphone");
  else if (action === "request-system-audio") void requestPermission("system-audio");
  else if (action === "settings" || action === "open-settings") {
    if (invoke) void invoke("open_settings_window").catch(reportError);
  }
  else if (action === "clear-error") { state.error = ""; render(); }
  else if (action === "clear-notice") { state.notice = ""; render(); }
}

function handleInput(event) {
  if (event.target.dataset.field === "library-search") {
    state.search = event.target.value;
    clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(() => void runBusy("search", refreshLibrary), 220);
  }
  if (event.target.dataset.field === "operator-note") {
    state.noteDraft = event.target.value;
    state.noteSaveState = "local";
    setNoteSaveCopy();
    scheduleNoteSave();
  }
  if (event.target.dataset.field === "library-operator-note") {
    if (!state.selected) return;
    state.selected.operatorNoteDraft = event.target.value;
    state.selected.operatorNoteSaveState = "local";
    setLibraryNoteSaveCopy();
    scheduleSelectedNoteSave();
  }
  if (event.target.dataset.field === "transcript-search") {
    state.transcriptQuery = event.target.value;
    render();
  }
  if (event.target.dataset.field === "meeting-title") {
    state.renameDraft = event.target.value;
  }
}

function handleChange(event) {
  if (event.target.dataset.field === "retention-days") {
    state.retentionDays = Number(event.target.value);
    render();
  }
  if (event.target.dataset.field === "attestation") {
    state.consent[event.target.dataset.attestation] = event.target.checked;
    render();
  }
  if (event.target.dataset.field === "operator-note") void flushPendingNoteSave();
  if (event.target.dataset.field === "library-operator-note") void flushSelectedNoteSave();
}

function handleKeydown(event) {
  if (event.key === "Escape" && state.modal) { state.modal = ""; render(); return; }
  if (event.key === "Escape" && state.meetingManagementOpen) { state.meetingManagementOpen = false; render(); return; }
  if (!event.metaKey || event.altKey || event.ctrlKey) return;
  if (event.key.toLowerCase() === "r" && canOpenStart(state.snapshot, state.permissions)) {
    event.preventDefault();
    openStart();
  }
  if (event.key.toLowerCase() === "k" && state.snapshot?.capture === "idle") {
    event.preventDefault();
    void openMeetings().then(() => document.querySelector("[data-field='library-search']")?.focus());
  }
}

function handleSubmit(event) {
  if (event.target.dataset.form !== "rename-meeting") return;
  event.preventDefault();
  void saveMeetingTitle();
}

async function initialize() {
  render();
  if (!invoke) return;
  try {
    await Promise.all([
      refreshSnapshot({ shouldRender: false }),
      refreshLibrary(),
      refreshPermissions(),
    ]);
  } catch (error) {
    state.error = String(error).replace(/^Error:\s*/, "") || "Yawn could not open its local workspace.";
  }
  render();
  window.setInterval(() => {
    if (shouldPollSnapshot(state.snapshot)) {
      void refreshSnapshot().catch(reportError);
    }
  }, 900);
}

document.addEventListener("click", handleClick);
document.addEventListener("input", handleInput);
document.addEventListener("change", handleChange);
document.addEventListener("keydown", handleKeydown);
document.addEventListener("submit", handleSubmit);
window.addEventListener("focus", refreshPermissionsOnReturn);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshPermissionsOnReturn();
});

void initialize();
