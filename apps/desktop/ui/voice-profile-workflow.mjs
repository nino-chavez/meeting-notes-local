import {
  enrollmentRecorderPresentation,
  operatingPointPresentation,
} from "./navigation-state.mjs";

// Per-sitting lifecycle copy is content-free by construction: the evidence
// store owns the state and the UI never exposes setup audio or a transcript.
const SITTING_STATE_COPY = {
  "recording-in-progress": "This recording did not finish. It will be set aside as a rehearsal.",
  "raw-retained": "Waiting for the app to derive voice material. The temporary recording is kept until that completes.",
  "cleanup-pending": "Voice material is stored. The app still has to delete the temporary recording.",
  saved: "Saved. The temporary recording has been deleted.",
  rehearsal: "Rehearsal only. It does not count toward setup.",
};

export function createVoiceProfileController({
  root = document,
  invoke,
  isActive = () => true,
} = {}) {
  const element = (selector) => {
    const found = root.querySelector(selector);
    if (!found) throw new Error(`Voice profile requires ${selector}.`);
    return found;
  };

  const profileLede = element("#profile-lede");
  const profileStatusTitle = element("#profile-status-title");
  const profileStatusCopy = element("#profile-status-copy");
  const profileFootnote = element("#profile-footnote");
  const profileSetup = element("#profile-setup");
  const profileNextStep = element("#profile-next-step");
  const profileEnrollmentGates = element("#profile-enrollment-gates");
  const profileRecorder = element("#profile-recorder");
  const profileRecorderEntry = element("#profile-recorder-entry");
  const profileSittings = element("#profile-sittings");
  const sittingForm = element("#sitting-form");
  const sittingSourceClass = element("#sitting-source-class");
  const sittingStart = element("#sitting-start");
  const sittingActive = element("#sitting-active");
  const sittingStop = element("#sitting-stop");
  const sittingError = element("#sitting-error");
  const sittingOutcome = element("#sitting-outcome");
  const operatingPointsSection = element("#profile-operating-points");
  const operatingPointsForm = element("#operating-points-form");
  const operatingPointsRows = element("#operating-points-rows");
  const operatingPointsError = element("#operating-points-error");
  const operatingPointsLoad = element("#operating-points-load");
  const operatingPointsBuild = element("#operating-points-build");
  const profileResetConfirmation = element("#profile-reset-confirmation");
  const profileResetConfirm = element("#profile-reset-confirm");
  const profileResetCancel = element("#profile-reset-cancel");
  const profileResetStatus = element("#profile-reset-status");

  let activationRevision = 0;
  let latestOperatingPoints = null;
  let operatingPointsBusy = false;
  let latestEnrollmentSurface = null;
  let latestProfileSnapshot = null;
  let sittingPollTimer = null;
  let sittingCommandPending = false;

  function current(revision) {
    return isActive() && revision === activationRevision;
  }

  function clearSittingPoll() {
    if (sittingPollTimer) window.clearTimeout(sittingPollTimer);
    sittingPollTimer = null;
  }

  function renderOperatingPointsSection(guidance) {
    const applies = guidance?.state === "choosing-operating-point";
    operatingPointsSection.hidden = !applies;
    if (!applies) {
      latestOperatingPoints = null;
      operatingPointsRows.disabled = true;
      operatingPointsBuild.disabled = true;
      operatingPointsError.hidden = true;
      operatingPointsError.textContent = "";
      operatingPointsRows.replaceChildren(
        Object.assign(document.createElement("legend"), {
          textContent: "Measured options",
        }),
      );
    }
  }

  function renderEnrollmentGuidance(snapshot) {
    const applies =
      snapshot?.state === "baseline-ready" && snapshot?.profileActive !== true;
    const guidance = applies ? snapshot?.guidedEnrollment : null;
    const nextStep = guidance?.nextStep;
    profileNextStep.hidden = !nextStep;
    profileNextStep.textContent = nextStep || "";
    const gates = applies && Array.isArray(guidance?.gates) ? guidance.gates : [];
    profileEnrollmentGates.hidden = gates.length === 0;
    profileEnrollmentGates.textContent = gates.join(" ");
    renderOperatingPointsSection(guidance);
  }

  function renderOperatingPointRows(response) {
    const rows = operatingPointPresentation(response?.points);
    if (response?.state !== "choices" || rows.length < 2 || !response?.choicesSha256) {
      latestOperatingPoints = null;
      operatingPointsRows.disabled = true;
      operatingPointsBuild.disabled = true;
      operatingPointsError.textContent =
        response?.message
        || "The measured options are unavailable right now. Try again.";
      operatingPointsError.hidden = false;
      return;
    }
    latestOperatingPoints = { choicesSha256: response.choicesSha256, rows };
    operatingPointsError.hidden = true;
    operatingPointsError.textContent = "";
    operatingPointsRows.replaceChildren(
      Object.assign(document.createElement("legend"), {
        textContent: "Measured options",
      }),
      ...rows.map((row) => {
        const label = document.createElement("label");
        label.className = "ys-radio-choice voice-profile-choice";
        const input = document.createElement("input");
        input.type = "radio";
        input.name = "operating-point";
        input.value = String(row.point.targetFrr);
        const text = document.createElement("span");
        const title = document.createElement("strong");
        title.textContent = `${row.label}.`;
        const costs = document.createElement("small");
        costs.textContent = row.costs;
        text.append(title, costs);
        label.append(input, text);
        return label;
      }),
    );
    operatingPointsRows.disabled = false;
    operatingPointsBuild.disabled = true;
    operatingPointsLoad.textContent = "Measure the options again";
  }

  function selectedOperatingPoint() {
    const checked = operatingPointsRows.querySelector(
      "input[name=\"operating-point\"]:checked",
    );
    if (!checked || !latestOperatingPoints) return null;
    const target = Number(checked.value);
    const row = latestOperatingPoints.rows.find(
      (candidate) => candidate.point.targetFrr === target,
    );
    return row ? { target, choicesSha256: latestOperatingPoints.choicesSha256 } : null;
  }

  async function loadOperatingPoints() {
    if (!invoke || operatingPointsBusy || !isActive()) return;
    const revision = activationRevision;
    operatingPointsBusy = true;
    operatingPointsLoad.disabled = true;
    try {
      const response = await invoke("preview_enrollment_operating_points").catch(() => null);
      if (current(revision)) renderOperatingPointRows(response);
    } finally {
      operatingPointsBusy = false;
      if (current(revision)) operatingPointsLoad.disabled = false;
    }
  }

  async function buildVoiceProfile(event) {
    event.preventDefault();
    if (!invoke || operatingPointsBusy || !isActive()) return;
    const selection = selectedOperatingPoint();
    if (!selection) {
      operatingPointsError.textContent = "Choose one measured option first.";
      operatingPointsError.hidden = false;
      return;
    }
    const revision = activationRevision;
    operatingPointsBusy = true;
    operatingPointsBuild.disabled = true;
    operatingPointsLoad.disabled = true;
    operatingPointsRows.disabled = true;
    operatingPointsBuild.textContent = "Building…";
    operatingPointsError.hidden = true;
    try {
      const snapshot = await invoke("preview_enrollment_build_profile", {
        selectedTarget: selection.target,
        choicesSha256: selection.choicesSha256,
      });
      if (!current(revision)) return;
      renderProfile(snapshot);
      const surface = await invoke("preview_enrollment_surface").catch(() => null);
      if (current(revision)) renderEnrollmentSittings(surface);
      profileStatusTitle.focus();
    } catch (error) {
      if (!current(revision)) return;
      operatingPointsRows.disabled = false;
      operatingPointsBuild.disabled = false;
      operatingPointsError.textContent =
        typeof error === "string"
          ? error
          : "The profile was not built. Review the options and try again.";
      operatingPointsError.hidden = false;
    } finally {
      operatingPointsBusy = false;
      if (current(revision)) {
        operatingPointsLoad.disabled = false;
        operatingPointsBuild.textContent = "Build voice profile";
      }
    }
  }

  function sittingAttemptRunning(surface) {
    const mode = enrollmentRecorderPresentation(surface).mode;
    return mode === "recording" || mode === "processing";
  }

  function scheduleSittingPoll() {
    clearSittingPoll();
    const revision = activationRevision;
    sittingPollTimer = window.setTimeout(async () => {
      sittingPollTimer = null;
      if (!invoke || !current(revision)) return;
      const wasRunning = sittingAttemptRunning(latestEnrollmentSurface);
      const surface = await invoke("preview_enrollment_surface").catch(() => null);
      if (!current(revision)) return;
      renderEnrollmentSittings(surface);
      if (wasRunning && !sittingAttemptRunning(surface)) {
        const snapshot = await invoke("preview_profile_snapshot").catch(() => null);
        if (current(revision) && snapshot) renderProfile(snapshot);
        if (current(revision)) renderEnrollmentSittings(surface);
      }
    }, 1500);
  }

  function syncGuidedSetupEntry() {
    if (profileSetup.dataset.action !== "setup") return;
    if (
      latestProfileSnapshot?.state !== "baseline-ready"
      || latestProfileSnapshot?.profilePresent !== false
      || latestProfileSnapshot?.profileActive === true
    ) {
      return;
    }
    const mode = enrollmentRecorderPresentation(latestEnrollmentSurface).mode;
    profileSetup.disabled = mode === "unavailable";
    profileStatusCopy.textContent =
      mode === "unavailable"
        ? "Private setup storage is ready. Guided setup is not part of this build."
        : "Private setup storage is ready. Setup recordings below are where you begin.";
  }

  function renderEnrollmentSittings(surface) {
    latestEnrollmentSurface = surface;
    const presentation = enrollmentRecorderPresentation(surface);
    profileRecorderEntry.hidden = !presentation.entryText;
    profileRecorderEntry.textContent = presentation.entryText;
    sittingForm.hidden = presentation.mode !== "ready";
    sittingActive.hidden = presentation.mode !== "recording";
    sittingOutcome.hidden = !presentation.outcomeText;
    sittingOutcome.textContent = presentation.outcomeText;
    if (presentation.mode !== "ready") {
      sittingError.hidden = true;
      sittingError.textContent = "";
    }
    sittingStart.disabled = sittingCommandPending;
    sittingStop.disabled = sittingCommandPending;
    const sittings = Array.isArray(surface?.sittings) ? surface.sittings : [];
    profileSittings.hidden = sittings.length === 0;
    profileSittings.replaceChildren(
      ...sittings.map((sitting) => {
        const item = document.createElement("li");
        const kind =
          sitting?.kind === "negative-source" ? "Comparison speech" : "Voice session";
        const copy = SITTING_STATE_COPY[sitting?.state] || "State unavailable.";
        item.textContent = `${kind}: ${copy}`;
        return item;
      }),
    );
    syncGuidedSetupEntry();
    if (presentation.mode === "recording" || presentation.mode === "processing") {
      scheduleSittingPoll();
    }
  }

  function selectedSittingRequest() {
    const kind =
      sittingForm.querySelector("input[name=\"sitting-kind\"]:checked")?.value
      || "operator-sitting";
    if (kind !== "negative-source") return { kind, sourceClass: null };
    const sourceClass =
      sittingSourceClass.querySelector("input[name=\"sitting-source-class\"]:checked")?.value
      || null;
    return { kind, sourceClass };
  }

  function syncSittingSourceClass() {
    const { kind } = selectedSittingRequest();
    sittingSourceClass.hidden = kind !== "negative-source";
  }

  async function startSittingRecording(event) {
    event.preventDefault();
    if (!invoke || sittingCommandPending || !isActive()) return;
    const { kind, sourceClass } = selectedSittingRequest();
    if (kind === "negative-source" && !sourceClass) {
      sittingError.textContent = "Choose where the comparison speech comes from first.";
      sittingError.hidden = false;
      return;
    }
    const revision = activationRevision;
    sittingCommandPending = true;
    sittingStart.disabled = true;
    sittingError.hidden = true;
    sittingError.textContent = "";
    try {
      const surface = await invoke("preview_enrollment_start_sitting", {
        kind,
        sourceClass,
      });
      sittingCommandPending = false;
      if (!current(revision)) return;
      renderEnrollmentSittings(surface);
      sittingStop.focus();
    } catch (error) {
      sittingCommandPending = false;
      if (!current(revision)) return;
      sittingStart.disabled = false;
      sittingError.textContent =
        typeof error === "string" ? error : "The setup recording could not start.";
      sittingError.hidden = false;
    }
  }

  async function stopSittingRecording() {
    if (!invoke || sittingCommandPending || !isActive()) return;
    const revision = activationRevision;
    sittingCommandPending = true;
    sittingStop.disabled = true;
    try {
      await invoke("preview_enrollment_stop_sitting");
    } catch {
      // The surface poll reports the authoritative outcome rather than a
      // second UI-local error path.
    }
    sittingCommandPending = false;
    if (!current(revision)) return;
    sittingActive.hidden = true;
    const surface = await invoke("preview_enrollment_surface").catch(() => null);
    if (!current(revision)) return;
    renderEnrollmentSittings(surface);
    if (sittingAttemptRunning(surface)) {
      scheduleSittingPoll();
    } else {
      const snapshot = await invoke("preview_profile_snapshot").catch(() => null);
      if (current(revision) && snapshot) renderProfile(snapshot);
      if (current(revision)) renderEnrollmentSittings(surface);
    }
  }

  function renderProfile(snapshot) {
    latestProfileSnapshot = snapshot;
    const state = snapshot?.state || "unavailable";
    profileResetConfirmation.hidden = true;
    profileResetStatus.hidden = true;
    profileResetStatus.textContent = "";
    profileResetConfirm.disabled = false;
    profileResetConfirm.textContent = "Delete voice profile";
    profileResetCancel.disabled = false;
    profileSetup.disabled = true;
    profileSetup.textContent = "Set up voice profile";
    profileSetup.dataset.action = "setup";
    renderEnrollmentGuidance(snapshot);
    // Presence and activation are separate lifecycle facts. An active profile
    // must never inherit the preserved-legacy copy below, which promises this
    // build will not activate the stored bytes it found.
    if (state === "baseline-ready" && snapshot?.profileActive === true) {
      profileLede.textContent = "A profile is active. Recording still requires headphones and only you near the microphone.";
      profileStatusTitle.textContent = "Voice isolation is on";
      profileStatusCopy.textContent = "This profile passed the app’s final checks before it was stored. It sets aside speech that does not match you; it does not name speakers.";
      profileFootnote.textContent = "Removing the profile deletes it, its calibrated setting, and its setup records. Meetings, transcripts, notes, and evidence remain.";
      profileSetup.disabled = false;
      profileSetup.textContent = "Reset stored profile";
      profileSetup.dataset.action = "reset";
      return;
    }
    if (state === "baseline-ready" && snapshot?.profilePresent === false) {
      profileLede.textContent = "Voice isolation is off. You can record now — one speaker, wearing headphones. A profile will let the app set aside speech that is not yours.";
      profileStatusTitle.textContent = "No profile is set up";
      profileStatusCopy.textContent = "Private setup storage is ready. Guided setup is not part of this build.";
      profileFootnote.textContent = "Opening this screen reads only the setup status. It never opens meetings or transcripts.";
      syncGuidedSetupEntry();
      return;
    }
    if (state === "baseline-ready" && snapshot?.profilePresent === true) {
      profileLede.textContent = "Stored profile material was found, but it is not active. Recording works the same either way — one speaker, wearing headphones.";
      profileStatusTitle.textContent = "Stored material is not active";
      profileStatusCopy.textContent = "This build will not turn these bytes on. You can remove them through a separate confirmation without changing any meeting.";
      profileFootnote.textContent = "Opening this screen reads only the setup status. Reset is the only action that opens and changes the stored profile slot.";
      profileSetup.disabled = false;
      profileSetup.textContent = "Reset stored profile";
      profileSetup.dataset.action = "reset";
      return;
    }
    if (state === "migration-review-required") {
      profileLede.textContent = "A profile from an earlier version was found. This build left it untouched and will not turn it on.";
      profileStatusTitle.textContent = "Earlier profile needs review";
      profileStatusCopy.textContent = "Preserve for review adds lifecycle records around the exact stored bytes. It does not turn them on or change them.";
      profileFootnote.textContent = "Leaving this screen keeps the stored profile unchanged. Removal stays a separate confirmed action.";
      profileSetup.disabled = false;
      profileSetup.textContent = "Preserve for review";
      profileSetup.dataset.action = "preserve";
      return;
    }
    if (state === "needs-attention") {
      profileLede.textContent = "Profile storage needs attention. Nothing was turned on or deleted.";
      profileStatusTitle.textContent = "Storage needs attention";
      profileStatusCopy.textContent = "Your retained meetings are still readable. Guided setup and reset stay unavailable in this build.";
      profileFootnote.textContent = "Opening this screen reads only the attention state. It never opens meetings or transcripts.";
      return;
    }
    profileLede.textContent = "This build could not read its own voice-setup state.";
    profileStatusTitle.textContent = "Status unavailable";
    profileStatusCopy.textContent = "Recording stays available under the current one-speaker limit. Retained meetings remain readable.";
    profileFootnote.textContent = "Try opening Settings again after the installation check finishes.";
  }

  function showProfileResetConfirmation() {
    if (profileSetup.disabled || profileSetup.dataset.action !== "reset") return;
    profileResetConfirmation.hidden = false;
    profileResetStatus.hidden = true;
    profileResetConfirm.disabled = false;
    profileResetCancel.disabled = false;
    profileResetConfirm.focus();
  }

  function cancelProfileReset() {
    profileResetConfirmation.hidden = true;
    profileResetStatus.hidden = true;
    profileSetup.focus();
  }

  async function resetStoredProfile() {
    if (!invoke || profileResetConfirm.disabled || !isActive()) return;
    const revision = activationRevision;
    profileResetConfirm.disabled = true;
    profileResetCancel.disabled = true;
    profileResetConfirm.textContent = "Deleting…";
    profileResetStatus.hidden = true;
    try {
      const snapshot = await invoke("preview_profile_reset", { confirmed: true });
      if (!current(revision)) return;
      renderProfile(snapshot);
      profileStatusCopy.textContent = "The stored voice profile was deleted. Meetings and their retained artifacts were not changed.";
      profileFootnote.textContent = "The reset journal retains only its completion count, latest event, fixed empty slots, and filesystem metadata.";
      profileStatusTitle.focus();
    } catch (error) {
      if (!current(revision)) return;
      profileResetConfirm.disabled = false;
      profileResetCancel.disabled = false;
      profileResetConfirm.textContent = "Delete voice profile";
      profileResetStatus.textContent = typeof error === "string" ? error : "The profile was not reset. Review the current status and try again.";
      profileResetStatus.hidden = false;
    }
  }

  async function preserveLegacyProfile() {
    if (!invoke || profileSetup.disabled || !isActive()) return;
    const revision = activationRevision;
    profileSetup.disabled = true;
    profileSetup.textContent = "Preserving…";
    try {
      const snapshot = await invoke("preview_profile_preserve_legacy");
      if (current(revision)) renderProfile(snapshot);
    } catch {
      if (!current(revision)) return;
      const snapshot = await invoke("preview_profile_snapshot").catch(() => ({ state: "unavailable" }));
      if (!current(revision)) return;
      renderProfile(snapshot);
      if (snapshot?.state === "migration-review-required") {
        profileStatusCopy.textContent = "The stored profile was left unchanged. Finish any active operation, then try again.";
      }
    }
  }

  function runProfileAction() {
    if (profileSetup.dataset.action === "setup") {
      if (profileSetup.disabled) return;
      profileRecorder.scrollIntoView({ behavior: "smooth", block: "start" });
      const focusTarget = !sittingForm.hidden
        ? sittingForm.querySelector("input[name=\"sitting-kind\"]:checked")
        : !sittingActive.hidden
          ? sittingStop
          : null;
      focusTarget?.focus({ preventScroll: true });
      return;
    }
    if (profileSetup.dataset.action === "preserve") {
      void preserveLegacyProfile();
      return;
    }
    if (profileSetup.dataset.action === "reset") showProfileResetConfirmation();
  }

  async function activate() {
    if (!invoke || !isActive()) return;
    const revision = ++activationRevision;
    try {
      const snapshot = await invoke("preview_profile_snapshot");
      if (current(revision)) renderProfile(snapshot);
    } catch {
      if (current(revision)) renderProfile({ state: "unavailable" });
    }
    const surface = await invoke("preview_enrollment_surface").catch(() => null);
    if (current(revision)) renderEnrollmentSittings(surface);
  }

  function deactivate() {
    activationRevision += 1;
    clearSittingPoll();
  }

  function renderBrowserUnavailable() {
    deactivate();
    profileStatusTitle.textContent = "Setup unavailable in this browser shell";
    profileStatusCopy.textContent = "The installed app reads private setup status and enforces its measured voice-profile gates. This prototype does not open or store setup audio.";
    profileRecorderEntry.textContent = "Install-level setup recording is not connected in this browser representation.";
    profileSetup.disabled = true;
  }

  profileSetup.addEventListener("click", runProfileAction);
  profileResetConfirm.addEventListener("click", resetStoredProfile);
  profileResetCancel.addEventListener("click", cancelProfileReset);
  sittingForm.addEventListener("submit", startSittingRecording);
  sittingForm.addEventListener("change", syncSittingSourceClass);
  sittingStop.addEventListener("click", stopSittingRecording);
  operatingPointsLoad.addEventListener("click", loadOperatingPoints);
  operatingPointsForm.addEventListener("submit", buildVoiceProfile);
  operatingPointsForm.addEventListener("change", () => {
    operatingPointsBuild.disabled = !selectedOperatingPoint();
  });

  return {
    activate,
    deactivate,
    renderBrowserUnavailable,
  };
}
