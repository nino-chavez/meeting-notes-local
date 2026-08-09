import {
  capturePresentation,
  recordPresentation,
} from "./state.mjs";

const root = document.documentElement;
const specimenMain = document.querySelector("#specimen-main");

const preferenceControls = [
  ["appearance-control", "appearance"],
  ["contrast-control", "contrast"],
  ["motion-control", "motion"],
  ["transparency-control", "transparency"],
];

for (const [id, key] of preferenceControls) {
  const control = document.querySelector(`#${id}`);
  control?.addEventListener("change", () => {
    root.dataset[key] = control.value;
  });
}

document.querySelector("#zoom-control")?.addEventListener("change", (event) => {
  specimenMain.dataset.zoom = event.currentTarget.value;
});

document.querySelector("#ia-geometry-control")?.addEventListener("change", (event) => {
  specimenMain.dataset.iaGeometry = event.currentTarget.value;
});

function selectTab(tab) {
  const tablist = tab.closest('[role="tablist"]');
  if (!tablist) return;
  const tabs = [...tablist.querySelectorAll(':scope > [role="tab"]')];
  for (const candidate of tabs) {
    const selected = candidate === tab;
    candidate.setAttribute("aria-selected", String(selected));
    candidate.tabIndex = selected ? 0 : -1;
    const panel = document.querySelector(`#${candidate.getAttribute("aria-controls")}`);
    if (panel) panel.hidden = !selected;
  }
}

for (const tablist of document.querySelectorAll('[role="tablist"]')) {
  const tabs = [...tablist.querySelectorAll(':scope > [role="tab"]')];
  for (const tab of tabs) {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const current = tabs.indexOf(tab);
      const previous = event.key === "ArrowLeft" || event.key === "ArrowUp";
      const nextIndex = event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (current + (previous ? -1 : 1) + tabs.length) % tabs.length;
      selectTab(tabs[nextIndex]);
      tabs[nextIndex].focus();
    });
  }
}

for (const disclosure of document.querySelectorAll("[data-disclosure]")) {
  disclosure.addEventListener("click", () => {
    const expanded = disclosure.getAttribute("aria-expanded") === "true";
    disclosure.setAttribute("aria-expanded", String(!expanded));
  });
}

const adaptiveOption = document.querySelector('[data-ia-option="adaptive-two-pane"]');
for (const control of document.querySelectorAll("[data-adaptive-open-record]")) {
  control.addEventListener("click", () => {
    adaptiveOption.dataset.compactView = "record";
  });
}
document.querySelector("[data-adaptive-back]")?.addEventListener("click", () => {
  adaptiveOption.dataset.compactView = "collection";
  document.querySelector("[data-adaptive-open-record]")?.focus();
});

const stackOption = document.querySelector('[data-ia-option="single-pane-stack"]');
for (const control of document.querySelectorAll("[data-stack-open-record]")) {
  control.addEventListener("click", () => {
    stackOption.dataset.stackView = "record";
  });
}
document.querySelector("[data-stack-back]")?.addEventListener("click", () => {
  stackOption.dataset.stackView = "collection";
  document.querySelector("[data-stack-open-record]")?.focus();
});

const captureTitle = document.querySelector("#capture-title");
const captureStatus = document.querySelector("#capture-status");
const captureStatusLabel = document.querySelector("#capture-status-label");
const captureDetail = document.querySelector("#capture-detail");
const captureActions = document.querySelector("#capture-actions");

function renderCaptureState(state) {
  const presentation = capturePresentation(state);
  captureTitle.textContent = presentation.title;
  captureStatus.dataset.state = presentation.statusState;
  captureStatusLabel.textContent = presentation.status;
  captureDetail.textContent = presentation.detail;
  captureActions.replaceChildren();
  presentation.actions.forEach((label, index) => {
    const button = document.createElement("button");
    button.className = "ys-button";
    button.type = "button";
    button.textContent = label;
    if (index === presentation.actions.length - 1 && state === "recording") button.dataset.variant = "live";
    if (index === presentation.actions.length - 1 && state === "degraded") button.dataset.tone = "error";
    if (index === presentation.actions.length - 1 && presentation.primaryDisabled) button.disabled = true;
    captureActions.append(button);
  });
  for (const control of document.querySelectorAll("[data-capture-state]")) {
    control.setAttribute("aria-pressed", String(control.dataset.captureState === state));
  }
}

for (const control of document.querySelectorAll("[data-capture-state]")) {
  control.addEventListener("click", () => renderCaptureState(control.dataset.captureState));
}

const recordTitle = document.querySelector("#record-specimen-title");
const recordMeta = document.querySelector("#record-specimen-meta");
const recordBody = document.querySelector("#record-specimen-body");
const recordNotice = document.querySelector("#record-specimen-notice");

function renderRecordState(state) {
  const presentation = recordPresentation(state);
  recordTitle.textContent = presentation.title;
  recordMeta.textContent = presentation.meta;
  recordBody.textContent = presentation.body;
  recordNotice.dataset.tone = presentation.tone;
  recordNotice.hidden = presentation.tone === "ready";
  recordNotice.textContent = presentation.tone === "error" ? "This record needs recovery." : "This is a bounded fallback state.";
  for (const control of document.querySelectorAll("[data-record-state]")) {
    control.setAttribute("aria-pressed", String(control.dataset.recordState === state));
  }
}

for (const control of document.querySelectorAll("[data-record-state]")) {
  control.addEventListener("click", () => renderRecordState(control.dataset.recordState));
}

const popoverTrigger = document.querySelector("#popover-trigger");
const popover = document.querySelector("#specimen-popover");
const popoverClose = document.querySelector("#popover-close");

function closePopover({ restoreFocus = true } = {}) {
  popover.hidden = true;
  popoverTrigger.setAttribute("aria-expanded", "false");
  if (restoreFocus) popoverTrigger.focus();
}

function openPopover() {
  popover.hidden = false;
  popoverTrigger.setAttribute("aria-expanded", "true");
  popoverClose.focus();
}

popoverTrigger?.addEventListener("click", () => {
  if (popover.hidden) openPopover();
  else closePopover();
});
popoverClose?.addEventListener("click", () => closePopover());

const dialog = document.querySelector("#specimen-dialog");
const dialogTrigger = document.querySelector("#dialog-trigger");
const dialogCancel = document.querySelector("#dialog-cancel");

dialogTrigger?.addEventListener("click", () => dialog.showModal());
dialogCancel?.addEventListener("click", () => dialog.close());
dialog?.addEventListener("close", () => dialogTrigger.focus());

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (dialog.open) {
    event.preventDefault();
    dialog.close();
    return;
  }
  if (!popover.hidden) {
    event.preventDefault();
    closePopover();
  }
});
