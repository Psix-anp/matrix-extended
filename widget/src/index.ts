import "./styles.css";

import { MatrixWidgetBridge, type BridgeStatus } from "./matrix";
import { WidgetStateModel } from "./model";
import {
  HEARTBEAT_INTERVAL_MS,
  buildConfirmation,
  buildEntityAction,
  buildHeartbeat,
  buildPanelAction,
  buildSubscribe,
  parseWidgetConfig,
  type WidgetLocale,
  type WidgetRequest,
  type WidgetResult,
} from "./protocol";
import { renderPanelHtml, type PendingConfirmationView } from "./render";

const rootElement = document.querySelector<HTMLElement>("#app");
if (!rootElement) throw new Error("Missing #app root");
const root: HTMLElement = rootElement;

const locale: WidgetLocale = navigator.language.toLowerCase().startsWith("ru") ? "ru" : "en";
const config = parseWidgetConfig(window.location.hash);
const model = new WidgetStateModel(config);
const bridge = new MatrixWidgetBridge(config);

let bridgeStatus: BridgeStatus = "idle";
let statusDetail = "";
let pendingConfirmation: { id: string; expiresAt: number } | null = null;
let lastActionStatus = "";

function statusLabel(): string {
  if (bridgeStatus === "ready" && model.connected) return locale === "ru" ? "Подключено" : "Connected";
  if (bridgeStatus === "denied") return locale === "ru" ? "Нет разрешений" : "Capabilities denied";
  if (bridgeStatus === "error") return locale === "ru" ? "Ошибка" : "Error";
  return locale === "ru" ? "Нет соединения" : "Disconnected";
}

function pendingView(): PendingConfirmationView | null {
  if (!pendingConfirmation) return null;
  const remaining = Math.max(0, Math.ceil((pendingConfirmation.expiresAt - Date.now()) / 1000));
  if (remaining <= 0) {
    pendingConfirmation = null;
    return null;
  }
  return { confirmationId: pendingConfirmation.id, expiresIn: remaining };
}

function render(): void {
  if (!model.snapshot) {
    root.innerHTML = `<main class="widget-shell empty"><p class="eyebrow">Matrix Extended</p><h1>${locale === "ru" ? "Панель управления" : "Control panel"}</h1><p>${statusLabel()}</p><p class="muted">${statusDetail}</p></main>`;
    return;
  }
  root.innerHTML = renderPanelHtml(model.snapshot, locale, pendingView());
  const status = root.querySelector<HTMLElement>(".connection-status");
  if (status) {
    status.textContent = statusLabel();
    status.dataset.state = bridgeStatus === "ready" && model.connected ? "connected" : bridgeStatus;
  }
  if (lastActionStatus) {
    const shell = root.querySelector<HTMLElement>(".widget-shell");
    shell?.insertAdjacentHTML("beforeend", `<p class="toast" role="status"></p>`);
    const toast = root.querySelector<HTMLElement>(".toast");
    if (toast) toast.textContent = lastActionStatus;
  }
}

async function sendTracked(request: WidgetRequest, label: string): Promise<void> {
  const requestId = typeof request.request_id === "string" ? request.request_id : null;
  if (requestId) model.trackRequestWithId(requestId, label);
  try {
    await bridge.send(request);
  } catch (error) {
    lastActionStatus = String(error);
    render();
  }
}

async function sendEntityControl(entityId: string, control: string, value?: unknown): Promise<void> {
  const requestId = crypto.randomUUID();
  await sendTracked(
    buildEntityAction(config, model.generation, entityId, control, value, requestId),
    `${entityId}:${control}`,
  );
}

async function sendPanelAction(actionId: string): Promise<void> {
  const requestId = crypto.randomUUID();
  await sendTracked(buildPanelAction(config, model.generation, actionId, requestId), actionId);
}

async function answerConfirmation(confirm: boolean): Promise<void> {
  if (!pendingConfirmation) return;
  const confirmationId = pendingConfirmation.id;
  pendingConfirmation = null;
  const requestId = crypto.randomUUID();
  render();
  await sendTracked(
    buildConfirmation(config, model.generation, confirmationId, confirm, requestId),
    confirm ? "confirmation" : "cancellation",
  );
}

bridge.onStatus((status, detail) => {
  bridgeStatus = status;
  statusDetail = detail ?? "";
  render();
  if (status === "ready") {
    void bridge.send(buildSubscribe(config)).catch((error: unknown) => {
      statusDetail = String(error);
      bridgeStatus = "error";
      render();
    });
  }
});

bridge.onMessage((message) => {
  if (message.op === "state") {
    if (model.accept(message)) render();
    return;
  }
  if (message.op === "error") {
    model.handleError(message);
    lastActionStatus = message.error || message.status;
    render();
    return;
  }

  const result = message as WidgetResult;
  const completed = model.completeRequest(result);
  if (result.status === "confirmation_required" && result.confirmation_id) {
    pendingConfirmation = {
      id: result.confirmation_id,
      expiresAt: Date.now() + Math.max(1, result.expires_in ?? 30) * 1000,
    };
  } else if (completed) {
    lastActionStatus = completed.status;
  }
  render();
});

root.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target.closest<HTMLElement>("button") : null;
  if (!target) return;

  if (target.dataset.confirm === "true") {
    void answerConfirmation(true);
    return;
  }
  if (target.dataset.confirm === "false") {
    void answerConfirmation(false);
    return;
  }
  if (target.dataset.actionId) {
    void sendPanelAction(target.dataset.actionId);
    return;
  }
  const entityId = target.dataset.entity;
  const control = target.dataset.control;
  if (!entityId || !control) return;
  let value: unknown = target.dataset.value;
  if (value === "true") value = true;
  else if (value === "false") value = false;
  else if (value === undefined) value = undefined;
  void sendEntityControl(entityId, control, value);
});

root.addEventListener("change", (event) => {
  const input = event.target;
  if (!(input instanceof HTMLInputElement || input instanceof HTMLSelectElement)) return;
  const entityId = input.dataset.entity;
  const control = input.dataset.control;
  if (!entityId || !control) return;

  let value: unknown;
  if (input instanceof HTMLInputElement && input.type === "checkbox") value = input.checked;
  else if (input instanceof HTMLInputElement && ["range", "number"].includes(input.type)) value = Number(input.value);
  else value = input.value;
  void sendEntityControl(entityId, control, value);
});

setInterval(() => {
  if (pendingConfirmation) render();
  if (bridgeStatus !== "ready") return;
  if (model.generation > 0) {
    void bridge.send(buildHeartbeat(config, model.generation)).catch(() => undefined);
  } else {
    void bridge.send(buildSubscribe(config)).catch(() => undefined);
  }
}, HEARTBEAT_INTERVAL_MS);

render();
bridge.start();
