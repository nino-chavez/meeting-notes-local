export const SURFACE_STATES = Object.freeze({
  primary: Object.freeze(["loading", "empty", "ready", "error"]),
  capture: Object.freeze(["consent", "recording", "degraded", "processing", "error"]),
});

export const STATE_LABELS = Object.freeze({
  loading: "Loading",
  empty: "Empty",
  ready: "Ready + selected",
  error: "Error",
  consent: "Consent + disabled",
  recording: "Recording",
  degraded: "Degraded capture",
  processing: "Processing",
});

export function normalizedOptions(input = {}) {
  const surface = input.surface === "capture" ? "capture" : "primary";
  const requestedState = String(input.state || "");
  const state = SURFACE_STATES[surface].includes(requestedState)
    ? requestedState
    : SURFACE_STATES[surface][surface === "primary" ? 2 : 0];
  return {
    surface,
    state,
    appearance: input.appearance === "dark" ? "dark" : "light",
    geometry: input.geometry === "minimum" ? "minimum" : "comfortable",
    presentation: input.presentation === true || input.presentation === "true",
  };
}

export function captureToolbarPresentation(state) {
  if (state === "recording") return { label: "Recording · both channels active", tone: "is-live", stop: true };
  if (state === "degraded") return { label: "Recording · channel needs attention", tone: "is-degraded", stop: true };
  if (state === "processing") return { label: "Transcribing locally", tone: "is-idle", stop: false };
  if (state === "error") return { label: "Needs attention", tone: "is-degraded", stop: false };
  return { label: "Not recording", tone: "is-idle", stop: false };
}

function optionsFromLocation() {
  const params = new URLSearchParams(window.location.search);
  return normalizedOptions({
    surface: params.get("surface"),
    state: params.get("state"),
    appearance: params.get("appearance"),
    geometry: params.get("geometry"),
    presentation: params.get("presentation"),
  });
}

function replaceLocation(options) {
  const params = new URLSearchParams();
  params.set("surface", options.surface);
  params.set("state", options.state);
  params.set("appearance", options.appearance);
  params.set("geometry", options.geometry);
  if (options.presentation) params.set("presentation", "true");
  history.replaceState(null, "", `${location.pathname}?${params.toString()}`);
}

function setHiddenByState(selector, state) {
  for (const element of document.querySelectorAll(selector)) {
    const target = element.dataset.primaryState || element.dataset.captureState;
    element.hidden = target !== state;
  }
}

function setSelectOptions(select, surface, state) {
  select.replaceChildren();
  for (const value of SURFACE_STATES[surface]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = STATE_LABELS[value] || value;
    option.selected = value === state;
    select.append(option);
  }
}

function focusSurfaceHeading(options) {
  const selector = options.surface === "primary"
    ? options.state === "ready" ? "#meeting-title" : `#primary-reference [data-primary-state="${options.state}"] strong, #primary-reference [data-primary-state="${options.state}"] h2`
    : `#capture-reference [data-capture-state="${options.state}"] h1`;
  const target = document.querySelector(selector);
  if (!target) return;
  target.tabIndex = -1;
  target.focus({ preventScroll: true });
}

function installRovingGroups() {
  for (const group of document.querySelectorAll("[data-roving]")) {
    group.addEventListener("keydown", (event) => {
      const controls = [...group.querySelectorAll(":scope > button:not(:disabled)")];
      if (!controls.length) return;
      const current = controls.indexOf(document.activeElement);
      const horizontal = group.dataset.roving === "horizontal";
      const previousKey = horizontal ? "ArrowLeft" : "ArrowUp";
      const nextKey = horizontal ? "ArrowRight" : "ArrowDown";
      let next = current;
      if (event.key === previousKey) next = current <= 0 ? controls.length - 1 : current - 1;
      else if (event.key === nextKey) next = current >= controls.length - 1 ? 0 : current + 1;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = controls.length - 1;
      else return;
      event.preventDefault();
      for (const control of controls) control.tabIndex = control === controls[next] ? 0 : -1;
      controls[next].focus();
      if (group.getAttribute("role") === "tablist") controls[next].click();
    });
  }
}

function installMeetingTabs() {
  const tabs = [...document.querySelectorAll('[role="tab"][aria-controls]')];
  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      const tablist = tab.closest('[role="tablist"]');
      if (!tablist) return;
      for (const peer of tablist.querySelectorAll('[role="tab"]')) {
        const selected = peer === tab;
        peer.setAttribute("aria-selected", String(selected));
        peer.tabIndex = selected ? 0 : -1;
        const panel = document.getElementById(peer.getAttribute("aria-controls"));
        if (panel) panel.hidden = !selected;
      }
    });
  }
  for (const link of document.querySelectorAll("[data-tab-target]")) {
    link.addEventListener("click", () => document.querySelector(`#${link.dataset.tabTarget}-tab`)?.click());
  }
}

function installMeetingRows() {
  for (const row of document.querySelectorAll(".ds-meeting-list-row")) {
    row.addEventListener("click", () => {
      for (const peer of document.querySelectorAll(".ds-meeting-list-row")) {
        const selected = peer === row;
        peer.classList.toggle("is-selected", selected);
        peer.setAttribute("aria-current", selected ? "page" : "false");
      }
    });
  }
}

function boot() {
  const root = document.documentElement;
  const body = document.body;
  const primary = document.querySelector("#primary-reference");
  const capture = document.querySelector("#capture-reference");
  const surfaceSelect = document.querySelector("#surface-select");
  const stateSelect = document.querySelector("#state-select");
  const appearanceSelect = document.querySelector("#appearance-select");
  const geometrySelect = document.querySelector("#geometry-select");
  const toolbarStatus = document.querySelector("#capture-toolbar-status");
  const toolbarStatusLabel = toolbarStatus.lastElementChild;
  const toolbarStop = document.querySelector("#capture-stop-toolbar");
  const toolbarCancel = document.querySelector("#capture-cancel-toolbar");
  const attestation = document.querySelector("#participant-attestation");
  const retention = document.querySelector("#reference-retention");
  const continueButton = document.querySelector("#capture-continue");
  let options = optionsFromLocation();

  function apply(next, { focus = false } = {}) {
    options = normalizedOptions({ ...options, ...next });
    root.dataset.theme = options.appearance;
    root.dataset.geometry = options.geometry;
    body.dataset.presentation = String(options.presentation);
    primary.hidden = options.surface !== "primary";
    capture.hidden = options.surface !== "capture";
    primary.dataset.referenceState = options.surface === "primary" ? options.state : "ready";
    capture.dataset.referenceState = options.surface === "capture" ? options.state : "consent";
    setHiddenByState("#primary-reference [data-primary-state]", primary.dataset.referenceState);
    setHiddenByState("#capture-reference [data-capture-state]", capture.dataset.referenceState);

    surfaceSelect.value = options.surface;
    setSelectOptions(stateSelect, options.surface, options.state);
    appearanceSelect.value = options.appearance;
    geometrySelect.value = options.geometry;

    const toolbar = captureToolbarPresentation(options.surface === "capture" ? options.state : "consent");
    toolbarStatus.className = `ds-status-indicator ${toolbar.tone}`;
    toolbarStatusLabel.textContent = toolbar.label;
    toolbarStop.hidden = !toolbar.stop;
    toolbarCancel.hidden = toolbar.stop;
    toolbarCancel.textContent = options.state === "processing" ? "Hide" : "Cancel";
    replaceLocation(options);
    if (focus) focusSurfaceHeading(options);
  }

  function openPrimary() { apply({ surface: "primary", state: "ready" }, { focus: true }); }
  function openCapture(state) { apply({ surface: "capture", state }, { focus: true }); }
  function updateConsentAction() { continueButton.disabled = !(attestation.checked && retention.value); }

  surfaceSelect.addEventListener("change", () => apply({
    surface: surfaceSelect.value,
    state: surfaceSelect.value === "primary" ? "ready" : "consent",
  }, { focus: true }));
  stateSelect.addEventListener("change", () => apply({ state: stateSelect.value }, { focus: true }));
  appearanceSelect.addEventListener("change", () => apply({ appearance: appearanceSelect.value }));
  geometrySelect.addEventListener("change", () => apply({ geometry: geometrySelect.value }));

  document.querySelector("#primary-record").addEventListener("click", () => openCapture("consent"));
  document.querySelector("#capture-cancel").addEventListener("click", openPrimary);
  document.querySelector("#capture-cancel-toolbar").addEventListener("click", openPrimary);
  document.querySelector("#capture-error-return").addEventListener("click", openPrimary);
  toolbarStop.addEventListener("click", () => openCapture("processing"));
  document.querySelector("#retry-system-audio").addEventListener("click", () => openCapture("recording"));
  attestation.addEventListener("change", updateConsentAction);
  retention.addEventListener("change", updateConsentAction);
  document.querySelector("#consent-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!continueButton.disabled) openCapture("recording");
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || options.surface !== "capture") return;
    if (["recording", "degraded"].includes(options.state)) return;
    event.preventDefault();
    openPrimary();
  });

  installRovingGroups();
  installMeetingTabs();
  installMeetingRows();
  updateConsentAction();
  apply(options);
}

if (typeof document !== "undefined") boot();
