import { mergePermissions } from "./view-model.mjs";

const invoke = window.__TAURI__?.core?.invoke;
const permissionsRoot = document.querySelector("#permissions");
const message = document.querySelector("#message");

let permissions = null;

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
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "refresh") void refresh();
  if (action === "microphone" || action === "system-audio") void request(action);
});

void refresh();
