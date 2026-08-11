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
  modal: "",
  noteDraft: "",
  noteLoadedFor: "",
  noteLoading: false,
  noteSaveQueue: Promise.resolve(),
  noteSaveState: "local",
  noteUnreadable: false,
  permissions: null,
  retentionDays: 7,
  search: "",
  searchTimer: null,
  selected: null,
  snapshot: null,
};

let noteSaveTimer;
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
      ${state.error ? `<aside class="toast" role="alert"><button type="button" data-action="clear-error" aria-label="Dismiss">×</button>${escapeHtml(state.error)}</aside>` : ""}
    </div>
  `;
  syncActivityClock();
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
        <textarea class="note-editor" data-field="operator-note" aria-label="Your meeting notes" placeholder="Write down the detail you will want to verify later." ${disabled ? "disabled" : ""}>${escapeHtml(state.noteDraft)}</textarea>
        <div class="capture-foot">
          <p>${state.noteUnreadable ? "This note could not be read, so Yawn will not overwrite it." : "Saved separately from the transcript. These are your notes, not generated claims."}</p>
        </div>
      </article>
      ${snapshot.turns?.length ? renderTranscript(snapshot.turns, terminal ? "Source transcript" : "Live transcript", terminal ? "The retained record for checking a detail that matters." : "Yawn adds local transcription here as it becomes available.") : ""}
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

function renderTranscript(turns, title, detail = "") {
  return `
    <section class="transcript-panel" aria-labelledby="transcript-heading">
      <div class="transcript-heading"><h3 id="transcript-heading">${escapeHtml(title)}</h3>${detail ? `<p>${escapeHtml(detail)}</p>` : ""}</div>
      ${turns.map((turn) => `
        <div class="transcript-line ${turn.withheld ? "withheld" : ""}">
          <time>${escapeHtml(timeLabel(turn.start))}</time>
          <p>${turn.withheld ? "This turn was withheld by the voice check." : escapeHtml(turn.text)}</p>
        </div>
      `).join("")}
    </section>
  `;
}

function renderMeeting() {
  const { row, note, transcript } = state.selected;
  const title = row.label || `Meeting · ${dateLabel(row.createdAtEpochSeconds)}`;
  const claims = note?.claims || [];
  const operatorNote = note?.operatorNote;
  const claimEvidence = state.selected.claimEvidence || {};
  return `
    <article class="meeting-page" aria-labelledby="meeting-title">
      <button class="text-button" type="button" data-action="meetings">Back to meetings</button>
      <p class="eyebrow">Saved on this Mac</p>
      <h1 class="meeting-title" id="meeting-title">${escapeHtml(title)}</h1>
      <div class="meeting-meta"><span>${escapeHtml(dateLabel(row.createdAtEpochSeconds))}</span><span>${escapeHtml(note?.state ? humanize(note.state) : "Loading note")}</span></div>
      ${note?.message && !claims.length ? `<p class="message-card ${note.state === "summary-failed" ? "attention" : ""}">${escapeHtml(note.message)}</p>` : ""}
      ${claims.length ? `
        <section class="draft-notice" aria-label="About this draft note">
          <p class="eyebrow">Draft note</p>
          <h2>Review before you rely on it.</h2>
          <p>These points were generated from the transcript. A summary can miss a commitment or join two nearby ideas, so each point keeps a path back to its source.</p>
        </section>
      ` : ""}
      <div class="meeting-review-grid">
        <section class="note-section" aria-labelledby="meeting-note-heading">
          <h3 id="meeting-note-heading">${claims.length ? "Points from the transcript" : "Draft note"}</h3>
          ${claims.length ? `<ul class="claim-list">${claims.map((claim) => `<li class="claim-item">
            <span class="claim-label">${escapeHtml(humanize(claim.claimType))}</span>
            <p>${escapeHtml(claim.claim)}</p>
            ${renderClaimEvidence(claim, claimEvidence[claim.ordinal])}
          </li>`).join("")}</ul>` : `<p class="quiet-copy">No generated meeting-note claims are available for this meeting.</p>`}
        </section>
        <section class="note-section your-notes-section" aria-labelledby="operator-note-heading">
          <h3 id="operator-note-heading">Your notes</h3>
          ${operatorNote?.unreadable
            ? `<p class="message-card attention">Yawn could not read this meeting’s personal note, so it was left unchanged.</p>`
            : operatorNote?.text
              ? `<div class="operator-note-copy">${escapeHtml(operatorNote.text)}</div>`
              : `<p class="quiet-copy">You did not add a personal note during this meeting.</p>`}
        </section>
      </div>
      ${transcript?.turns?.length ? renderTranscript(transcript.turns, "Source transcript", "The retained record. Use it to check a decision, owner, or follow-up that matters.") : transcript?.message ? `<section class="note-section"><p class="message-card">${escapeHtml(transcript.message)}</p></section>` : ""}
      <section class="retention-copy" aria-labelledby="retention-heading">
        <h3 id="retention-heading">Audio retention</h3>
        <p>${escapeHtml(note?.audioRetention?.message || "Audio-retention details are unavailable for this meeting.")}</p>
      </section>
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

function attestation(name, label) {
  return `<label class="check-row"><input type="checkbox" data-field="attestation" data-attestation="${name}" ${state.consent[name] ? "checked" : ""} /><span>${escapeHtml(label)}</span></label>`;
}

function setNoteSaveCopy() {
  const target = document.querySelector("#note-save-state");
  if (target) target.textContent = noteSaveCopy();
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
  await runBusy("meeting", async () => {
    const note = await invoke("library_open_note", { handle });
    const transcript = note.transcriptHandle
      ? await invoke("library_open_transcript", { handle: note.transcriptHandle })
      : null;
    state.selected = { row, note, transcript, claimEvidence: {} };
    state.activeView = "meeting";
  });
}

async function openClaimEvidence(ordinal) {
  const selection = state.selected;
  if (!selection?.row?.meetingId || !Number.isFinite(ordinal)) return;
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

async function flushPendingNoteSave() {
  if (noteSaveTimer !== undefined) {
    clearTimeout(noteSaveTimer);
    noteSaveTimer = undefined;
    await queueNoteSave();
  }
  await state.noteSaveQueue;
}

async function openMeetings() {
  state.selected = null;
  state.activeView = "home";
  if (!invoke) {
    render();
    return;
  }
  await runBusy("library", refreshLibrary);
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
  else if (action === "close-start") { state.modal = ""; render(); }
  else if (action === "start-recording") void startRecording();
  else if (action === "stop-recording") void stopRecording();
  else if (action === "dismiss-current") void dismissCurrent();
  else if (action === "record-another") void recordAnother();
  else if (action === "open-meeting") void openMeeting(control.dataset.handle);
  else if (action === "open-claim-evidence") void openClaimEvidence(Number(control.dataset.ordinal));
  else if (action === "retry-startup") void retryStartup();
  else if (action === "request-microphone") void requestPermission("microphone");
  else if (action === "request-system-audio") void requestPermission("system-audio");
  else if (action === "settings" || action === "open-settings") {
    if (invoke) void invoke("open_settings_window").catch(reportError);
  }
  else if (action === "clear-error") { state.error = ""; render(); }
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
}

function handleKeydown(event) {
  if (event.key === "Escape" && state.modal) { state.modal = ""; render(); return; }
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
window.addEventListener("focus", refreshPermissionsOnReturn);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshPermissionsOnReturn();
});

void initialize();
