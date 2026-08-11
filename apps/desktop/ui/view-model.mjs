const CAPTURE_COPY = Object.freeze({
  idle: {
    eyebrow: "Ready when you are",
    title: "Your next meeting starts here.",
    detail: "Nothing is recording.",
    tone: "ready",
  },
  arming: {
    eyebrow: "Preparing capture",
    title: "Getting your audio ready.",
    detail: "Yawn is not recording until both audio sources are ready.",
    tone: "working",
  },
  recording: {
    eyebrow: "Recording locally",
    title: "Stay in the conversation.",
    detail: "Add a short note whenever something matters.",
    tone: "recording",
  },
  stopping: {
    eyebrow: "Stopping capture",
    title: "Finishing the recording.",
    detail: "Keep this window open while Yawn closes the audio safely.",
    tone: "working",
  },
  captured: {
    eyebrow: "Audio saved locally",
    title: "Making your transcript.",
    detail: "Your recording is safe while Yawn prepares the written record.",
    tone: "working",
  },
  transcribing: {
    eyebrow: "Transcribing locally",
    title: "Making your transcript.",
    detail: "This can take a moment. Your own notes remain available below.",
    tone: "working",
  },
  summarizing: {
    eyebrow: "Preparing notes",
    title: "Finishing your meeting note.",
    detail: "Yawn is preparing a local note from the completed transcript.",
    tone: "working",
  },
  "transcript-ready": {
    eyebrow: "Transcript ready",
    title: "Your meeting is ready to read.",
    detail: "Your transcript is already saved on this Mac. Go back to Meetings or record another meeting.",
    tone: "complete",
  },
  "transcription-failed": {
    eyebrow: "Needs attention",
    title: "The transcript was not created.",
    detail: "Yawn will tell you what remains available instead of calling this meeting complete.",
    tone: "attention",
  },
  "summary-failed": {
    eyebrow: "Needs attention",
    title: "The meeting note was not created.",
    detail: "The transcript remains available. Yawn will not call a note complete when it was not created.",
    tone: "attention",
  },
  "recovered-interrupted": {
    eyebrow: "Interrupted",
    title: "This meeting did not finish.",
    detail: "Review what survived before you start another recording.",
    tone: "attention",
  },
});

const CAPTURE_ACTIVITY_COPY = Object.freeze({
  arming: {
    label: "Preparing capture",
    detail: "Checking that both audio sources are ready. Nothing is recording yet.",
    tone: "working",
  },
  recording: {
    label: "Recording locally",
    detail: "Both audio sources are being captured on this Mac.",
    tone: "recording",
  },
  stopping: {
    label: "Stopping recording",
    detail: "Closing both audio streams safely before transcription starts.",
    tone: "working",
  },
  captured: {
    label: "Checking captured audio",
    detail: "Verifying the finalized audio before Yawn makes the transcript.",
    tone: "working",
  },
  transcribing: {
    label: "Transcribing locally",
    detail: "The captured audio is saved. Yawn is making the transcript on this Mac.",
    tone: "working",
  },
  summarizing: {
    label: "Preparing meeting notes",
    detail: "The transcript is ready. Yawn is preparing the local meeting note.",
    tone: "working",
  },
});

export function capturePresentation(snapshot) {
  const capture = snapshot?.capture || "idle";
  const presentation = CAPTURE_COPY[capture] || {
    eyebrow: "Needs attention",
    title: "Yawn needs attention.",
    detail: "The current recording state could not be read.",
    tone: "attention",
  };
  return { capture, ...presentation };
}

export function captureActivity(snapshot) {
  const capture = snapshot?.capture || "idle";
  const activity = CAPTURE_ACTIVITY_COPY[capture];
  return activity ? { capture, ...activity } : null;
}

export function captureActivityElapsedSeconds(snapshot, nowEpochSeconds = Date.now() / 1000) {
  if (!captureActivity(snapshot)) return null;
  const startedAt = Number(snapshot?.capture_state_started_at_epoch_seconds);
  if (!Number.isFinite(startedAt) || !Number.isFinite(nowEpochSeconds)) return null;
  return Math.max(0, Math.floor(nowEpochSeconds - startedAt));
}

export function transcriptionWorkerHeartbeatAgeSeconds(snapshot, nowEpochSeconds = Date.now() / 1000) {
  if (snapshot?.capture !== "transcribing") return null;
  const observedAt = Number(snapshot?.transcription_last_worker_heartbeat_at_epoch_seconds);
  if (!Number.isFinite(observedAt) || !Number.isFinite(nowEpochSeconds)) return null;
  return Math.max(0, Math.floor(nowEpochSeconds - observedAt));
}

export function canStartMeeting(snapshot) {
  return snapshot?.startup === "ready" && snapshot?.capture === "idle";
}

export function canOpenStart(snapshot, permission) {
  return canStartMeeting(snapshot) && permissionSummary(permission).state === "ready";
}

export function mergePermissions(previous, received) {
  const preserveMeasured = (reported, earlier) => (
    reported === "unmeasured" && earlier !== undefined && earlier !== null ? earlier : reported
  );
  return {
    ...previous,
    ...received,
    microphone: preserveMeasured(received.microphone, previous?.microphone),
    systemAudio: preserveMeasured(received.systemAudio, previous?.systemAudio),
  };
}

export function captureIsInProgress(snapshot) {
  return ["arming", "recording", "stopping", "captured", "transcribing", "summarizing"].includes(snapshot?.capture);
}

export function shouldPollSnapshot(snapshot) {
  return snapshot?.startup !== "ready"
    || captureIsInProgress(snapshot)
    || snapshot?.capture === "transcript-ready";
}

export function permissionSummary(permission) {
  if (!permission) {
    return { state: "checking", title: "Checking audio access", detail: "Yawn checks access on this Mac before the first recording." };
  }
  if (permission.probeUnavailable) {
    return { state: "attention", title: "Audio access could not be checked", detail: "Open Settings to check microphone and system-audio access." };
  }
  if (permission.microphone === "authorized" && permission.systemAudio === "authorized") {
    return { state: "ready", title: "Audio access is ready", detail: "Microphone and system audio are available to Yawn." };
  }
  if (permission.microphone === "denied" || permission.microphone === "restricted") {
    return { state: "attention", title: "Microphone access is needed", detail: "Allow Yawn to use the microphone before recording." };
  }
  if (permission.microphone === "authorized" && permission.systemAudio === "unmeasured") {
    return { state: "setup", title: "Allow system audio", detail: "Microphone access is ready. Let Yawn verify its capture helper before recording." };
  }
  if (["unavailable", "unsupported", "unknown"].includes(permission.systemAudio)) {
    return { state: "attention", title: "System audio needs attention", detail: "Open Settings to check system-audio access before recording." };
  }
  return { state: "setup", title: "Set up audio access", detail: "Allow microphone and system audio before your first recording." };
}

export function retentionLabel(days) {
  return `${days} ${Number(days) === 1 ? "day" : "days"}`;
}

export function humanize(value) {
  return String(value || "").replace(/[-_]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
