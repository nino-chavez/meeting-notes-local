import { mergePermissions } from "./view-model.mjs";

const invoke = window.__TAURI__?.core?.invoke;
const permissionsRoot = document.querySelector("#permissions");
const modelsRoot = document.querySelector("#models");
const modelMessage = document.querySelector("#model-message");
const message = document.querySelector("#message");

let permissions = null;
let models = null;
let modelLoadError = "";
let modelPoll = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function humanize(value) {
  return String(value || "unknown").replace(/[-_]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function tone(value) {
  return value === "authorized" ? "ready" : ["denied", "restricted", "unavailable", "unsupported", "unknown"].includes(value) ? "attention" : "neutral";
}

function byteSizeLabel(bytes) {
  const value = Math.max(0, Number(bytes) || 0);
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)} GB`;
  if (value >= 1_000_000) return `${Math.round(value / 1_000_000)} MB`;
  return `${Math.round(value / 1_000)} KB`;
}

function row(title, value, detail, action = "") {
  return `
    <div class="permission-line">
      <div class="permission-copy"><strong>${escapeHtml(title)}</strong><p>${escapeHtml(detail)}</p></div>
      ${action || `<span class="state" data-tone="${tone(value)}">${escapeHtml(humanize(value))}</span>`}
    </div>
  `;
}

function render() {
  if (!permissions) {
    permissionsRoot.innerHTML = row("Checking access", "checking", "Yawn is checking the permissions this Mac reports.");
    return;
  }
  const microphoneAction = permissions.microphone === "not-determined"
    ? `<button class="allow-button" type="button" data-action="microphone">Allow microphone</button>`
    : "";
  const systemAction = permissions.systemAudio === "unmeasured"
    ? `<button class="allow-button" type="button" data-action="system-audio">Allow system audio</button>`
    : "";
  permissionsRoot.innerHTML = [
    row("Microphone", permissions.microphone, "Yawn uses this to capture your voice.", microphoneAction),
    row("System audio", permissions.systemAudio, "Yawn verifies that its capture helper can access meeting audio. This check does not save audio.", systemAction),
  ].join("");
}

function renderModels() {
  if (!models) {
    modelsRoot.innerHTML = row("Checking speech model", "checking", "Yawn is checking what is stored on this Mac.");
    modelMessage.textContent = modelLoadError;
    modelMessage.dataset.tone = modelLoadError ? "attention" : "neutral";
    return;
  }
  const busy = models.changeActive;
  modelsRoot.setAttribute("aria-busy", busy ? "true" : "false");
  modelsRoot.innerHTML = models.options.map((option) => {
    const selected = models.selectedModelId === option.id;
    const disabled = !models.canChange || busy;
    const status = option.active
      ? `<span class="state" data-tone="ready">In use</span>`
      : option.stored
        ? `<span class="state">On this Mac</span>`
        : `<span class="model-size">${byteSizeLabel(option.downloadBytes)}</span>`;
    const progress = selected && busy
      ? `<div class="model-progress"><progress max="${Math.max(1, models.totalBytes)}" value="${Math.min(models.totalBytes, models.downloadedBytes)}"></progress><small>${models.state === "verifying" ? "Checking the downloaded files…" : `${byteSizeLabel(models.downloadedBytes)} of ${byteSizeLabel(models.totalBytes)}`}</small></div>`
      : "";
    const use = option.active
      ? ""
      : `<button class="allow-button" type="button" data-action="use-model" data-model-id="${escapeHtml(option.id)}" ${disabled ? "disabled" : ""}>${option.stored ? "Use this model" : "Download and use"}</button>`;
    const remove = option.stored && !option.active
      ? `<button class="quiet-button" type="button" data-action="remove-model" data-model-id="${escapeHtml(option.id)}" data-model-title="${escapeHtml(option.title)}" ${disabled ? "disabled" : ""}>Remove download</button>`
      : "";
    return `
      <div class="model-line">
        <div class="model-copy">
          <div class="model-title-row"><strong>${escapeHtml(option.title)}</strong>${status}</div>
          <p>${escapeHtml(option.detail)}</p>
          ${progress}
        </div>
        <div class="model-actions">${use}${remove}</div>
      </div>
    `;
  }).join("");
  const hasInactiveDownload = models.options.some((option) => option.stored && !option.active);
  modelMessage.textContent = models.error || models.unavailableReason || (hasInactiveDownload
    ? "Inactive downloads can be removed to free space."
    : "You can download the other model at any time.");
  modelMessage.dataset.tone = models.error ? "attention" : "neutral";
}

function scheduleModelPoll() {
  clearTimeout(modelPoll);
  if (models?.changeActive) {
    modelPoll = setTimeout(() => void refreshModels(), 500);
  }
}

async function refreshModels() {
  if (!invoke) {
    modelMessage.textContent = "Open Settings from the Yawn desktop app.";
    return;
  }
  try {
    models = await invoke("transcript_model_settings");
    modelLoadError = "";
  } catch {
    models = null;
    modelLoadError = "Yawn could not check the saved speech model.";
  }
  renderModels();
  scheduleModelPoll();
}

async function useModel(modelId) {
  if (!invoke) return;
  modelMessage.textContent = "Starting the model change…";
  try {
    await invoke("install_transcript_model", { modelId });
    await refreshModels();
  } catch (error) {
    modelMessage.textContent = String(error || "Yawn could not change the speech model.");
    modelMessage.dataset.tone = "attention";
  }
}

async function removeModel(modelId, title) {
  if (!invoke) return;
  if (!window.confirm(`Remove ${title} from this Mac? You can download it again later.`)) return;
  modelMessage.textContent = `Removing ${title}…`;
  try {
    models = await invoke("remove_transcript_model", { modelId });
    renderModels();
  } catch (error) {
    modelMessage.textContent = String(error || "Yawn could not remove that speech model.");
    modelMessage.dataset.tone = "attention";
  }
}

async function refresh() {
  if (!invoke) {
    message.textContent = "Open Settings from the Yawn desktop app.";
    return;
  }
  message.textContent = "Checking audio access…";
  try {
    permissions = mergePermissions(permissions, await invoke("first_run_permissions"));
    message.textContent = permissions.probeUnavailable ? "Yawn could not check audio access. Reopen the app and try again." : "";
  } catch {
    message.textContent = "Yawn could not check audio access.";
  }
  render();
}

async function request(kind) {
  if (!invoke) return;
  const command = kind === "microphone" ? "first_run_request_microphone" : "first_run_request_system_audio";
  message.textContent = kind === "microphone" ? "Waiting for macOS…" : "Checking system audio…";
  try {
    permissions = mergePermissions(permissions, await invoke(command));
    message.textContent = "";
  } catch {
    message.textContent = "Yawn could not update this permission.";
  }
  render();
}

document.addEventListener("click", (event) => {
  const control = event.target.closest("[data-action]");
  const action = control?.dataset.action;
  if (action === "refresh") void refresh();
  if (action === "microphone" || action === "system-audio") void request(action);
  if (action === "use-model") void useModel(control.dataset.modelId);
  if (action === "remove-model") void removeModel(control.dataset.modelId, control.dataset.modelTitle);
});

void refresh();
void refreshModels();
