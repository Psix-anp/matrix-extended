import { describe, expect, it } from "vitest";

import { renderPanelHtml } from "../src/render";
import type { PanelSnapshot } from "../src/protocol";

const snapshot: PanelSnapshot = {
  schema: 1,
  op: "state",
  room_id: "!room:example.org",
  panel_id: "living",
  generation: 4,
  revision: 8,
  title: "Гостиная",
  entities: [
    {
      entity_id: "sensor.temperature",
      label: "Температура",
      domain: "sensor",
      state: "23.4",
      available: true,
      attributes: { unit_of_measurement: "°C" },
      controls: [],
    },
    {
      entity_id: "light.main",
      label: "Свет",
      domain: "light",
      state: "on",
      available: true,
      attributes: { brightness_pct: 61 },
      controls: ["toggle", "brightness"],
    },
    {
      entity_id: "cover.curtain",
      label: "Шторы",
      domain: "cover",
      state: "open",
      available: true,
      attributes: { position: 70 },
      controls: ["open", "stop", "close", "position"],
    },
    {
      entity_id: "climate.living",
      label: "Климат",
      domain: "climate",
      state: "heat",
      available: true,
      attributes: {
        current_temperature: 22.8,
        target_temperature: 21,
        hvac_modes: ["off", "heat", "auto"],
      },
      controls: ["temperature", "hvac_mode"],
    },
    {
      entity_id: "media_player.living",
      label: "Музыка",
      domain: "media_player",
      state: "playing",
      available: true,
      attributes: {
        volume_pct: 42,
        muted: false,
        title: "Time",
        artist: "Pink Floyd",
      },
      controls: ["previous", "play_pause", "next", "mute", "volume"],
    },
    {
      entity_id: "switch.hidden_control",
      label: "Недоступный switch",
      domain: "switch",
      state: "unavailable",
      available: false,
      attributes: {},
      controls: [],
    },
  ],
  actions: [
    { id: "scene_movie", label: "Кино", confirmation_required: false },
    { id: "alarm_off", label: "Снять охрану", confirmation_required: true },
  ],
};

describe("renderPanelHtml", () => {
  it("renders read-only sensors without invented controls", () => {
    const html = renderPanelHtml(snapshot, "ru");
    expect(html).toContain("Температура");
    expect(html).toContain("23.4 °C");
    expect(html).not.toContain('data-entity="sensor.temperature" data-control=');
  });

  it("renders only controls advertised by the backend snapshot", () => {
    const html = renderPanelHtml(snapshot, "ru");
    expect(html).toContain('data-entity="light.main" data-control="toggle"');
    expect(html).toContain('data-entity="light.main" data-control="brightness"');
    expect(html).toContain('data-entity="cover.curtain" data-control="position"');
    expect(html).toContain('data-entity="climate.living" data-control="hvac_mode"');
    expect(html).toContain('data-entity="media_player.living" data-control="play_pause"');
    expect(html).not.toContain('data-entity="light.main" data-control="color_temp"');
  });

  it("shows media metadata and bounded player controls", () => {
    const html = renderPanelHtml(snapshot, "ru");
    expect(html).toContain("Pink Floyd");
    expect(html).toContain("Time");
    expect(html).toContain('data-control="volume"');
    expect(html).toContain('data-control="mute"');
  });

  it("marks unavailable entities and keeps them non-interactive", () => {
    const html = renderPanelHtml(snapshot, "ru");
    expect(html).toContain("Недоступный switch");
    expect(html).toContain("entity-card unavailable");
    expect(html).not.toContain('data-entity="switch.hidden_control" data-control="toggle"');
  });

  it("renders panel actions with confirmation metadata", () => {
    const html = renderPanelHtml(snapshot, "ru");
    expect(html).toContain('data-action-id="scene_movie"');
    expect(html).toContain('data-action-id="alarm_off"');
    expect(html).toContain('data-confirmation-required="true"');
  });

  it("supports Russian and English UI labels", () => {
    const ru = renderPanelHtml(snapshot, "ru");
    const en = renderPanelHtml(snapshot, "en");
    expect(ru).toContain("Нет соединения");
    expect(en).toContain("Disconnected");
    expect(ru).toContain("Открыть");
    expect(en).toContain("Open");
  });
});
