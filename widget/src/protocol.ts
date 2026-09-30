export const WIDGET_EVENT_TYPE = "io.psix.matrix_extended.widget.v1";
export const WIDGET_SCHEMA = 1 as const;
export const WIDGET_SEND_CAPABILITY = `org.matrix.msc3819.send.to_device:${WIDGET_EVENT_TYPE}`;
export const WIDGET_RECEIVE_CAPABILITY = `org.matrix.msc3819.receive.to_device:${WIDGET_EVENT_TYPE}`;
export const HEARTBEAT_INTERVAL_MS = 30_000;

export type WidgetLocale = "en" | "ru";

export interface WidgetConfig {
  roomId: string;
  panelId: string;
  widgetId: string;
  integrationUserId: string;
  integrationDeviceId: string;
}

export interface EntitySnapshot {
  entity_id: string;
  label: string;
  domain: string;
  state: string;
  available: boolean;
  attributes: Record<string, unknown>;
  controls: string[];
}

export interface PanelActionSnapshot {
  id: string;
  label: string;
  confirmation_required: boolean;
}

export interface PanelSnapshot {
  schema: 1;
  op: "state";
  room_id: string;
  panel_id: string;
  generation: number;
  revision: number;
  title: string;
  entities: EntitySnapshot[];
  actions: PanelActionSnapshot[];
}

export interface WidgetResult {
  schema: 1;
  op: "result";
  room_id: string;
  panel_id: string;
  generation: number;
  request_id?: string;
  status: string;
  confirmation_id?: string;
  expires_in?: number;
}

export interface WidgetError {
  schema: 1;
  op: "error";
  room_id: string;
  panel_id: string;
  generation: number;
  request_id?: string;
  status: string;
  error?: string;
}

export type WidgetInboundMessage = PanelSnapshot | WidgetResult | WidgetError;

export type WidgetRequest = Record<string, unknown> & {
  schema: 1;
  op: string;
  room_id: string;
  panel_id: string;
  generation: number;
};

function required(params: URLSearchParams, key: string): string {
  const value = params.get(key)?.trim() ?? "";
  if (!value) throw new Error(`Missing Widget configuration: ${key}`);
  return value;
}

export function parseWidgetConfig(fragment: string): WidgetConfig {
  const params = new URLSearchParams(fragment.replace(/^#/, ""));
  const roomId = required(params, "room_id");
  const panelId = required(params, "panel_id");
  const widgetId = required(params, "widget_id");
  const integrationUserId = required(params, "integration_user_id");
  const integrationDeviceId = required(params, "integration_device_id");
  if (!roomId.startsWith("!") || !roomId.includes(":")) {
    throw new Error("Widget room_id must be a resolved Matrix room ID");
  }
  if (!integrationUserId.startsWith("@") || !integrationUserId.includes(":")) {
    throw new Error("Widget integration_user_id must be a Matrix user ID");
  }
  return { roomId, panelId, widgetId, integrationUserId, integrationDeviceId };
}

function base(config: WidgetConfig, generation: number): WidgetRequest {
  return {
    schema: WIDGET_SCHEMA,
    room_id: config.roomId,
    panel_id: config.panelId,
    generation,
    op: "",
  };
}

export function buildSubscribe(config: WidgetConfig): WidgetRequest {
  return { ...base(config, 0), op: "subscribe" };
}

export function buildHeartbeat(config: WidgetConfig, generation: number): WidgetRequest {
  return { ...base(config, generation), op: "heartbeat" };
}

export function buildEntityAction(
  config: WidgetConfig,
  generation: number,
  entityId: string,
  control: string,
  value?: unknown,
  requestId: string = crypto.randomUUID(),
): WidgetRequest {
  const request: WidgetRequest = {
    ...base(config, generation),
    op: "action",
    request_id: requestId,
    kind: "entity_control",
    entity_id: entityId,
    control,
  };
  if (value !== undefined) request.value = value;
  return request;
}

export function buildPanelAction(
  config: WidgetConfig,
  generation: number,
  actionId: string,
  requestId: string = crypto.randomUUID(),
): WidgetRequest {
  return {
    ...base(config, generation),
    op: "action",
    request_id: requestId,
    kind: "panel_action",
    action_id: actionId,
  };
}

export function buildConfirmation(
  config: WidgetConfig,
  generation: number,
  confirmationId: string,
  confirm: boolean,
  requestId: string = crypto.randomUUID(),
): WidgetRequest {
  return {
    ...base(config, generation),
    op: confirm ? "confirm" : "cancel",
    request_id: requestId,
    confirmation_id: confirmationId,
  };
}

export function isWidgetInboundMessage(value: unknown): value is WidgetInboundMessage {
  if (!value || typeof value !== "object") return false;
  const raw = value as Record<string, unknown>;
  return (
    raw.schema === WIDGET_SCHEMA &&
    typeof raw.op === "string" &&
    ["state", "result", "error"].includes(raw.op) &&
    typeof raw.room_id === "string" &&
    typeof raw.panel_id === "string" &&
    Number.isInteger(raw.generation)
  );
}
