export const CAPTURE_STATES = Object.freeze([
  "consent",
  "arming",
  "recording",
  "degraded",
  "stopping",
  "processing",
  "ready",
  "failure",
  "recovered",
]);

export const CAPTURE_PRESENTATIONS = Object.freeze({
  consent: {
    title: "Before you start",
    status: "Not recording",
    statusState: "ready",
    detail: "The other people on this call must know they are being recorded. Yawn cannot tell them.",
    actions: ["Cancel", "Continue"],
    primaryDisabled: true,
    live: false,
  },
  arming: {
    title: "Recording starts in five seconds",
    status: "Armed, not recording",
    statusState: "warning",
    detail: "Cancel remains available for the full countdown. No audio is open yet.",
    actions: ["Cancel countdown"],
    primaryDisabled: false,
    live: false,
  },
  recording: {
    title: "Recording",
    status: "Recording",
    statusState: "recording",
    detail: "Microphone and system audio are arriving. Your note saves on this Mac.",
    actions: ["Stop recording"],
    primaryDisabled: false,
    live: true,
  },
  degraded: {
    title: "Recording degraded",
    status: "Recording degraded",
    statusState: "degraded",
    detail: "System audio stopped. Microphone capture continues and this warning stays with the record.",
    actions: ["Stop recording"],
    primaryDisabled: false,
    live: true,
  },
  stopping: {
    title: "Stopping safely",
    status: "Recording is closing",
    statusState: "recording",
    detail: "Capture remains live until both audio files close. Stop is unavailable during this transition.",
    actions: ["Stopping…"],
    primaryDisabled: true,
    live: true,
  },
  processing: {
    title: "Making the transcript",
    status: "Processing on this Mac",
    statusState: "processing",
    detail: "You can use the rest of Yawn. Progress remains in the toolbar with a return path.",
    actions: ["Return to meetings"],
    primaryDisabled: false,
    live: false,
  },
  ready: {
    title: "Transcript ready",
    status: "Ready to review",
    statusState: "ready",
    detail: "The retained transcript is ready. No automatic note is implied.",
    actions: ["Open transcript", "Record another"],
    primaryDisabled: false,
    live: false,
  },
  failure: {
    title: "Transcript unavailable",
    status: "Needs attention",
    statusState: "error",
    detail: "Recording audio and the operator note remain available for recovery. This attempt is not complete.",
    actions: ["View recovery"],
    primaryDisabled: false,
    live: false,
  },
  recovered: {
    title: "Interrupted recording recovered",
    status: "Recovered, not complete",
    statusState: "warning",
    detail: "Recovered audio remains available. Interruption is preserved and never promoted to completion.",
    actions: ["Review recovered files"],
    primaryDisabled: false,
    live: false,
  },
});

export const RECORD_STATES = Object.freeze([
  "note",
  "transcript-only",
  "metadata-only",
  "summary-failed",
  "transcript-unavailable",
  "meeting-unavailable",
]);

export const RECORD_PRESENTATIONS = Object.freeze({
  note: {
    title: "Design-system handoff",
    meta: "Friday · 31 minutes · Transcript retained",
    body: "The operator note is retained. Automatic notes remain unavailable in this specimen.",
    tone: "ready",
  },
  "transcript-only": {
    title: "Design-system handoff",
    meta: "Transcript retained · No operator note",
    body: "The transcript is the durable source record. A missing note is not an error.",
    tone: "information",
  },
  "metadata-only": {
    title: "Design-system handoff",
    meta: "Meeting metadata retained · No transcript",
    body: "This meeting has no readable transcript. The surface does not invent one.",
    tone: "warning",
  },
  "summary-failed": {
    title: "Design-system handoff",
    meta: "Transcript retained · Automatic note unavailable",
    body: "The automatic note failed its checks. Read the retained transcript instead.",
    tone: "warning",
  },
  "transcript-unavailable": {
    title: "Transcript unavailable",
    meta: "Recording audio retained for recovery",
    body: "The attempt did not produce a transcript. It is not shown as complete.",
    tone: "error",
  },
  "meeting-unavailable": {
    title: "Meeting unavailable",
    meta: "The retained meeting could not be opened",
    body: "The surface stops here and preserves the local diagnostic path.",
    tone: "error",
  },
});

export function consentReady({ startup, retention, participant, accuracy, localProcessing }) {
  return startup === "ready"
    && retention === "selected"
    && participant === true
    && accuracy === true
    && localProcessing === true;
}

export function capturePresentation(state) {
  if (!CAPTURE_STATES.includes(state)) return CAPTURE_PRESENTATIONS.consent;
  return CAPTURE_PRESENTATIONS[state];
}

export function recordPresentation(state) {
  if (!RECORD_STATES.includes(state)) return RECORD_PRESENTATIONS.note;
  return RECORD_PRESENTATIONS[state];
}

export function normalizePreference(value, allowed) {
  return allowed.includes(value) ? value : "system";
}
