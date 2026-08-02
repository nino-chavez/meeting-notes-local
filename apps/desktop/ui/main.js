const invoke = window.__TAURI__?.core?.invoke;

const screens = new Map(
  [...document.querySelectorAll(".screen")].map((screen) => [screen.id, screen]),
);
const headerState = document.querySelector("#header-state");
const releaseBadge = document.querySelector("#release-badge");
const meetingLabel = document.querySelector("#meeting-id");
const startForm = document.querySelector("#start-form");
const startButton = document.querySelector("#start-button");
const startError = document.querySelector("#start-error");
const stopButton = document.querySelector("#stop-button");
const stopError = document.querySelector("#stop-error");
const retryStartup = document.querySelector("#retry-startup");
const libraryLink = document.querySelector("#library-link");
const libraryList = document.querySelector("#library-list");
const libraryNotice = document.querySelector("#library-notice");
const retention = document.querySelector("#retention-days");
const checks = [
  document.querySelector("#consent-check"),
  document.querySelector("#headphones-check"),
  document.querySelector("#room-check"),
];

let lastSnapshot = null;
let pollTimer = null;
let startedAt = null;
let elapsedTimer = null;
let libraryViewActive = false;

function showScreen(id) {
  for (const [screenId, screen] of screens) {
    screen.classList.toggle("active", screenId === id);
  }
}

function setError(element, message) {
  element.textContent = message || "The operation could not complete.";
  element.hidden = false;
}

function clearError(element) {
  element.textContent = "";
  element.hidden = true;
}

function startIsAllowed() {
  return lastSnapshot?.retention_operational === true
    && checks.every((check) => check.checked)
    && retention.value !== "";
}

function updateStartButton() {
  startButton.disabled = !startIsAllowed() || startButton.dataset.busy === "true";
}

function formatElapsed(seconds) {
  const safe = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}

function beginElapsed(epochSeconds) {
  startedAt = Number(epochSeconds) * 1000;
  const render = () => {
    const elapsed = startedAt ? (Date.now() - startedAt) / 1000 : 0;
    document.querySelector("#elapsed-time").textContent = formatElapsed(elapsed);
  };
  render();
  if (!elapsedTimer) elapsedTimer = window.setInterval(render, 1000);
}

function endElapsed() {
  if (elapsedTimer) window.clearInterval(elapsedTimer);
  elapsedTimer = null;
  startedAt = null;
}

function renderTranscript(snapshot) {
  renderTurns(
    document.querySelector("#transcript-turns"),
    document.querySelector("#transcript-warning"),
    snapshot.turns,
    snapshot.warnings,
  );
}

function renderTurns(container, warning, turns, warnings) {
  container.replaceChildren();
  const safeWarnings = Array.isArray(warnings) ? warnings : [];
  warning.hidden = safeWarnings.length === 0;
  warning.textContent = safeWarnings.join(" ");
  for (const turn of turns || []) {
    const row = document.createElement("section");
    row.className = "turn";
    const meta = document.createElement("div");
    meta.className = "turn-meta";
    const speaker = document.createElement("strong");
    speaker.textContent = turn.speaker || "Unattributed";
    const time = document.createElement("time");
    time.textContent = formatElapsed(turn.start || 0);
    meta.append(speaker, time);
    const text = document.createElement("p");
    text.textContent = turn.text || "";
    row.append(meta, text);
    container.append(row);
  }
  if (!container.children.length) {
    const empty = document.createElement("p");
    empty.className = "empty-transcript";
    empty.textContent = "No speech was detected in this capture.";
    container.append(empty);
  }
}

function formatMeetingTime(epochSeconds) {
  const value = Number(epochSeconds) * 1000;
  if (!Number.isFinite(value) || value <= 0) return "Retained meeting";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function renderLibrary(snapshot) {
  libraryList.replaceChildren();
  libraryNotice.hidden = true;
  libraryNotice.textContent = "";
  document.querySelector("#library-copy").textContent = snapshot.message || "Opening retained Preview meetings on this Mac.";
  if (snapshot.state !== "populated") {
    const empty = document.createElement("p");
    empty.className = "library-empty";
    empty.textContent = snapshot.state === "empty"
      ? "No retained Preview meetings yet. Finish a Preview recording to see it here."
      : "The Preview library is not available right now. Reopen the app and try again.";
    libraryList.append(empty);
    showScreen("library-screen");
    return;
  }
  for (const row of snapshot.rows || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "library-row";
    button.dataset.meetingId = row.meetingId;
    button.dataset.label = row.label || "Untitled meeting";
    button.disabled = row.transcriptAvailable !== true;
    const summary = document.createElement("span");
    const label = document.createElement("strong");
    label.textContent = row.label || "Untitled meeting";
    const time = document.createElement("small");
    time.textContent = formatMeetingTime(row.createdAtEpochSeconds);
    summary.append(label, time);
    const action = document.createElement("span");
    action.textContent = row.transcriptAvailable ? "View transcript" : "Transcript unavailable";
    button.append(summary, action);
    libraryList.append(button);
  }
  showScreen("library-screen");
}

function renderStartup(state) {
  const labels = {
    "shell-rendered": ["Opening the local shell", "Opening"],
    checking: ["Checking bundled files", "Checking"],
    "runtime-missing": ["This installation is incomplete", "Reinstall required"],
    "service-timeout": ["The local worker did not answer", "Check again"],
    "diagnostic-written": ["A private diagnostic was saved", "Needs attention"],
    retrying: ["Checking bundled files again", "Checking"],
    "reinstall-required": ["This installation must be repaired", "Reinstall required"],
  };
  const [heading, badge] = labels[state] || labels["diagnostic-written"];
  document.querySelector("#runtime-status").textContent = heading;
  document.querySelector("#runtime-pill").textContent = badge;
  document.querySelector("#startup-title").textContent =
    state === "runtime-missing" || state === "reinstall-required"
      ? "This build cannot start a meeting."
      : "Checking this installation.";
  retryStartup.hidden = !["service-timeout", "diagnostic-written"].includes(state);
  showScreen("startup-screen");
}

function render(snapshot) {
  lastSnapshot = snapshot;
  const startup = snapshot.startup || "diagnostic-written";
  const capture = snapshot.capture || "idle";
  document.documentElement.dataset.startupState = startup;
  document.documentElement.dataset.captureState = capture;
  const preview = snapshot.preview === true;
  releaseBadge.textContent = preview ? "Preview" : "Internal alpha";
  libraryLink.hidden = !preview || !["idle", "transcript-ready"].includes(capture) || startup !== "ready";
  meetingLabel.textContent = snapshot.meeting_id ? `Meeting ${snapshot.meeting_id.slice(0, 8)}` : "";

  if (startup !== "ready") {
    headerState.textContent = "Nothing is recording";
    endElapsed();
    renderStartup(startup);
    return;
  }

  switch (capture) {
    case "idle":
      headerState.textContent = "Ready · nothing is recording";
      endElapsed();
      showScreen("idle-screen");
      if (!snapshot.retention_operational) {
        setError(startError, snapshot.error || "Audio retention needs attention before another meeting can start.");
      }
      updateStartButton();
      break;
    case "arming":
      headerState.textContent = "Preparing · nothing is recording";
      endElapsed();
      showScreen("arming-screen");
      break;
    case "recording":
      headerState.textContent = snapshot.degraded ? "Recording · channel needs attention" : "Recording · both channels active";
      stopButton.disabled = false;
      document.querySelector("#capture-health").textContent = snapshot.degraded
        ? "Recording continues, but one channel reported a problem."
        : "Microphone and system audio are both arriving.";
      document.querySelector("#mic-state").textContent = snapshot.mic_state || "Active";
      document.querySelector("#system-state").textContent = snapshot.system_state || "Active";
      beginElapsed(snapshot.started_at_epoch_seconds);
      showScreen("recording-screen");
      break;
    case "stopping":
      headerState.textContent = "Stopping and flushing audio";
      stopButton.disabled = true;
      document.querySelector("#capture-health").textContent = "Finalizing both local audio files.";
      showScreen("recording-screen");
      break;
    case "captured":
    case "transcribing":
      headerState.textContent = "Transcribing locally";
      endElapsed();
      showScreen("processing-screen");
      break;
    case "transcript-ready":
      headerState.textContent = "Transcript ready · nothing is recording";
      endElapsed();
      renderTranscript(snapshot);
      showScreen("transcript-screen");
      break;
    default:
      headerState.textContent = "Nothing is recording · needs attention";
      endElapsed();
      document.querySelector("#error-detail").textContent = snapshot.error || "The attempt stopped before a validated transcript was ready.";
      showScreen("error-screen");
  }
}

async function openLibrary() {
  if (!invoke || lastSnapshot?.preview !== true) return;
  libraryViewActive = true;
  if (pollTimer) window.clearTimeout(pollTimer);
  pollTimer = null;
  document.querySelector("#library-copy").textContent = "Opening retained Preview meetings on this Mac.";
  libraryList.replaceChildren();
  showScreen("library-screen");
  try {
    renderLibrary(await invoke("preview_library_snapshot"));
  } catch {
    renderLibrary({ state: "unavailable", rows: [], message: "The Preview library is unavailable right now." });
  }
}

async function openLibraryTranscript(meetingId) {
  if (!invoke || !meetingId) return;
  try {
    const result = await invoke("preview_library_open_transcript", { meetingId });
    if (result.state !== "transcript") {
      setError(libraryNotice, result.message);
      return;
    }
    renderTurns(
      document.querySelector("#library-transcript-turns"),
      document.querySelector("#library-transcript-warning"),
      result.turns,
      result.warnings,
    );
    showScreen("library-transcript-screen");
  } catch {
    setError(libraryNotice, "That transcript could not be opened. Reopen Library and try again.");
  }
}

function schedulePoll(delay) {
  if (libraryViewActive) return;
  if (pollTimer) window.clearTimeout(pollTimer);
  pollTimer = window.setTimeout(refresh, delay);
}

async function refresh() {
  if (libraryViewActive) return;
  if (!invoke) {
    render({ startup: "diagnostic-written", capture: "idle", error: "The local application bridge is unavailable." });
    return;
  }
  try {
    const snapshot = await invoke("app_snapshot");
    render(snapshot);
    const active = ["arming", "recording", "stopping", "captured", "transcribing"].includes(snapshot.capture);
    schedulePoll(active ? 400 : 1500);
  } catch {
    render({ startup: "diagnostic-written", capture: "idle", error: "The local safety check could not finish." });
    schedulePoll(2000);
  }
}

function clearAttemptReview(clearRetention = false) {
  checks.forEach((check) => { check.checked = false; });
  if (clearRetention) retention.value = "";
  updateStartButton();
}

for (const field of checks) field.addEventListener("change", updateStartButton);
retention.addEventListener("change", () => {
  clearAttemptReview();
});

startForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError(startError);
  if (!startIsAllowed() || !invoke) return;
  const request = {
    retentionDays: Number(retention.value),
    attestation: {
      participantsConsented: checks[0].checked,
      headphones: checks[1].checked,
      operatorAlone: checks[2].checked,
    },
  };
  clearAttemptReview();
  startButton.dataset.busy = "true";
  startButton.textContent = "Preparing…";
  updateStartButton();
  try {
    await invoke("start_meeting", request);
    await refresh();
  } catch (error) {
    setError(startError, String(error));
  } finally {
    startButton.dataset.busy = "false";
    startButton.textContent = "Start recording";
    updateStartButton();
  }
});

stopButton.addEventListener("click", async () => {
  clearError(stopError);
  stopButton.disabled = true;
  stopButton.textContent = "Stopping…";
  try {
    await invoke("stop_meeting");
    await refresh();
  } catch (error) {
    setError(stopError, String(error));
    stopButton.disabled = false;
  } finally {
    stopButton.textContent = "Stop recording";
  }
});

document.querySelector("#new-meeting").addEventListener("click", async () => {
  if (invoke) await invoke("dismiss_meeting");
  clearAttemptReview(true);
  await refresh();
});

document.querySelector("#recover-button").addEventListener("click", async () => {
  if (invoke) await invoke("dismiss_meeting");
  clearAttemptReview(true);
  await refresh();
});

retryStartup.addEventListener("click", async () => {
  if (invoke) await invoke("retry_startup");
  await refresh();
});

libraryLink.addEventListener("click", openLibrary);
libraryList.addEventListener("click", (event) => {
  const row = event.target.closest("button[data-meeting-id]");
  if (row) openLibraryTranscript(row.dataset.meetingId);
});
document.querySelector("#library-back").addEventListener("click", () => {
  libraryViewActive = false;
  refresh();
});
document.querySelector("#library-transcript-back").addEventListener("click", openLibrary);

renderStartup("shell-rendered");
refresh();
