import { en } from "./i18n/en";
import { ru } from "./i18n/ru";
import type { EntitySnapshot, PanelSnapshot, WidgetLocale } from "./protocol";

export interface PendingConfirmationView {
  confirmationId: string;
  expiresIn: number;
}

type Messages = { [K in keyof typeof en]: string };

function messages(locale: WidgetLocale): Messages {
  return locale === "ru" ? ru : en;
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function attr(value: unknown): string {
  return escapeHtml(value);
}

function controlButton(
  entity: EntitySnapshot,
  control: string,
  label: string,
  value?: string | number | boolean,
): string {
  const valueAttr = value === undefined ? "" : ` data-value="${attr(value)}"`;
  return `<button type="button" class="control-button" data-entity="${attr(entity.entity_id)}" data-control="${attr(control)}"${valueAttr}>${escapeHtml(label)}</button>`;
}

function rangeControl(
  entity: EntitySnapshot,
  control: string,
  label: string,
  value: number,
): string {
  return `<label class="range-control"><span>${escapeHtml(label)}</span><input type="range" min="0" max="100" step="1" value="${attr(value)}" data-entity="${attr(entity.entity_id)}" data-control="${attr(control)}"><output>${attr(value)}%</output></label>`;
}

function entitySummary(entity: EntitySnapshot): string {
  const a = entity.attributes;
  if (entity.domain === "sensor" || entity.domain === "binary_sensor") {
    const unit = typeof a.unit_of_measurement === "string" ? ` ${a.unit_of_measurement}` : "";
    return `${escapeHtml(entity.state)}${escapeHtml(unit)}`;
  }
  if (entity.domain === "climate") {
    const current = a.current_temperature;
    const target = a.target_temperature;
    const parts: string[] = [];
    if (typeof current === "number") parts.push(`${current}°`);
    if (typeof target === "number") parts.push(`→ ${target}°`);
    return parts.length ? escapeHtml(parts.join(" ")) : escapeHtml(entity.state);
  }
  if (entity.domain === "media_player") {
    const title = typeof a.title === "string" ? a.title : "";
    const artist = typeof a.artist === "string" ? a.artist : "";
    if (title || artist) return escapeHtml([artist, title].filter(Boolean).join(" — "));
  }
  return escapeHtml(entity.state);
}

function renderControls(entity: EntitySnapshot, t: Messages): string {
  if (!entity.available || !entity.controls.length) return "";
  const controls = new Set(entity.controls);
  const out: string[] = [];
  const a = entity.attributes;

  if (controls.has("toggle")) {
    out.push(controlButton(entity, "toggle", entity.state === "on" ? t.off : t.on));
  }
  if (controls.has("brightness")) {
    const value = typeof a.brightness_pct === "number" ? a.brightness_pct : 0;
    out.push(rangeControl(entity, "brightness", t.brightness, value));
  }
  if (controls.has("open")) out.push(controlButton(entity, "open", t.open));
  if (controls.has("stop")) out.push(controlButton(entity, "stop", t.stop));
  if (controls.has("close")) out.push(controlButton(entity, "close", t.close));
  if (controls.has("position")) {
    const value = typeof a.position === "number" ? a.position : 0;
    out.push(rangeControl(entity, "position", t.position, value));
  }
  if (controls.has("temperature")) {
    const value = typeof a.target_temperature === "number" ? a.target_temperature : "";
    out.push(`<label class="number-control"><span>${escapeHtml(t.temperature)}</span><input type="number" inputmode="decimal" value="${attr(value)}" data-entity="${attr(entity.entity_id)}" data-control="temperature"></label>`);
  }
  if (controls.has("hvac_mode")) {
    const modes = Array.isArray(a.hvac_modes) ? a.hvac_modes.filter((v): v is string => typeof v === "string") : [];
    const options = modes.map((mode) => `<option value="${attr(mode)}"${mode === entity.state ? " selected" : ""}>${escapeHtml(mode)}</option>`).join("");
    out.push(`<label class="select-control"><span>${escapeHtml(t.hvacMode)}</span><select data-entity="${attr(entity.entity_id)}" data-control="hvac_mode">${options}</select></label>`);
  }
  if (controls.has("previous")) out.push(controlButton(entity, "previous", `⏮ ${t.previous}`));
  if (controls.has("play_pause")) out.push(controlButton(entity, "play_pause", `⏯ ${t.playPause}`));
  if (controls.has("next")) out.push(controlButton(entity, "next", `${t.next} ⏭`));
  if (controls.has("mute")) {
    const muted = a.muted === true;
    out.push(`<label class="toggle-control"><input type="checkbox" ${muted ? "checked " : ""}data-entity="${attr(entity.entity_id)}" data-control="mute"><span>${escapeHtml(t.mute)}</span></label>`);
  }
  if (controls.has("volume")) {
    const value = typeof a.volume_pct === "number" ? a.volume_pct : 0;
    out.push(rangeControl(entity, "volume", t.volume, value));
  }
  return `<div class="entity-controls">${out.join("")}</div>`;
}

function renderEntity(entity: EntitySnapshot, t: Messages): string {
  const classes = `entity-card${entity.available ? "" : " unavailable"}`;
  return `<section class="${classes}" data-domain="${attr(entity.domain)}"><div class="entity-heading"><div><strong>${escapeHtml(entity.label)}</strong><small>${escapeHtml(entity.entity_id)}</small></div><span class="entity-state">${entity.available ? entitySummary(entity) : escapeHtml(t.unavailable)}</span></div>${renderControls(entity, t)}</section>`;
}

export function renderPanelHtml(
  snapshot: PanelSnapshot,
  locale: WidgetLocale,
  pendingConfirmation?: PendingConfirmationView | null,
): string {
  const t = messages(locale);
  const entities = snapshot.entities.map((entity) => renderEntity(entity, t)).join("");
  const actions = snapshot.actions.length
    ? `<section class="panel-actions"><h2>${escapeHtml(t.actions)}</h2><div class="action-grid">${snapshot.actions.map((action) => `<button type="button" class="panel-action" data-action-id="${attr(action.id)}" data-confirmation-required="${action.confirmation_required ? "true" : "false"}">${escapeHtml(action.label)}</button>`).join("")}</div></section>`
    : "";
  const confirmation = pendingConfirmation
    ? `<div class="confirmation-backdrop" role="dialog" aria-modal="true" aria-labelledby="confirmation-title"><section class="confirmation-card"><h2 id="confirmation-title">${escapeHtml(t.confirmationTitle)}</h2><p>${escapeHtml(t.confirmationText)}</p><p class="muted">${escapeHtml(t.confirmationExpires)} (${attr(pendingConfirmation.expiresIn)}s)</p><div class="action-grid"><button type="button" data-confirm="true">${escapeHtml(t.confirm)}</button><button type="button" data-confirm="false">${escapeHtml(t.cancel)}</button></div></section></div>`
    : "";

  return `<main class="widget-shell"><header class="widget-header"><div><p class="eyebrow">Matrix Extended</p><h1>${escapeHtml(snapshot.title)}</h1></div><span class="connection-status" data-state="disconnected">${escapeHtml(t.disconnected)}</span></header><section class="entity-grid">${entities}</section>${actions}<p class="fallback-text">${escapeHtml(t.fallback)}</p>${confirmation}</main>`;
}
