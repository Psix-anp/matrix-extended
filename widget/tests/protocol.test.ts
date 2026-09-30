import { describe, expect, it } from "vitest";

import {
  HEARTBEAT_INTERVAL_MS,
  WIDGET_EVENT_TYPE,
  WIDGET_RECEIVE_CAPABILITY,
  WIDGET_SEND_CAPABILITY,
  buildEntityAction,
  buildSubscribe,
  parseWidgetConfig,
} from "../src/protocol";
import { WidgetStateModel } from "../src/model";

const config = {
  roomId: "!room:example.org",
  panelId: "living",
  widgetId: "widget-1",
  integrationUserId: "@ha:example.org",
  integrationDeviceId: "HADEVICE",
};

describe("Widget protocol", () => {
  it("uses the exact MSC3819 to-device capabilities", () => {
    expect(WIDGET_EVENT_TYPE).toBe("io.psix.matrix_extended.widget.v1");
    expect(WIDGET_SEND_CAPABILITY).toBe(
      "org.matrix.msc3819.send.to_device:io.psix.matrix_extended.widget.v1",
    );
    expect(WIDGET_RECEIVE_CAPABILITY).toBe(
      "org.matrix.msc3819.receive.to_device:io.psix.matrix_extended.widget.v1",
    );
  });

  it("parses only non-secret fragment configuration", () => {
    const parsed = parseWidgetConfig(
      "#room_id=%21room%3Aexample.org&panel_id=living&widget_id=widget-1&integration_user_id=%40ha%3Aexample.org&integration_device_id=HADEVICE",
    );
    expect(parsed).toEqual(config);
    expect(JSON.stringify(parsed)).not.toMatch(/token|password|secret/i);
  });

  it("subscribes at generation zero and uses a safe heartbeat interval", () => {
    expect(buildSubscribe(config)).toEqual({
      schema: 1,
      op: "subscribe",
      room_id: config.roomId,
      panel_id: config.panelId,
      generation: 0,
    });
    expect(HEARTBEAT_INTERVAL_MS).toBeGreaterThanOrEqual(20_000);
    expect(HEARTBEAT_INTERVAL_MS).toBeLessThan(90_000);
  });

  it("builds bounded entity actions without HA service payloads", () => {
    const request = buildEntityAction(config, 3, "light.living_room", "brightness", 42);
    expect(request.schema).toBe(1);
    expect(request.op).toBe("action");
    expect(request.kind).toBe("entity_control");
    expect(request.entity_id).toBe("light.living_room");
    expect(request.control).toBe("brightness");
    expect(request.value).toBe(42);
    expect(request.request_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(JSON.stringify(request)).not.toMatch(/service|target|template|yaml/i);
  });
});

describe("WidgetStateModel", () => {
  it("ignores stale revisions and accepts a newer generation", () => {
    const model = new WidgetStateModel(config);
    expect(
      model.accept({
        schema: 1,
        op: "state",
        room_id: config.roomId,
        panel_id: config.panelId,
        generation: 2,
        revision: 4,
        title: "Living",
        entities: [],
        actions: [],
      }),
    ).toBe(true);
    expect(model.revision).toBe(4);

    expect(
      model.accept({
        schema: 1,
        op: "state",
        room_id: config.roomId,
        panel_id: config.panelId,
        generation: 2,
        revision: 3,
        title: "Old",
        entities: [],
        actions: [],
      }),
    ).toBe(false);
    expect(model.snapshot?.title).toBe("Living");

    expect(
      model.accept({
        schema: 1,
        op: "state",
        room_id: config.roomId,
        panel_id: config.panelId,
        generation: 3,
        revision: 1,
        title: "Repaired",
        entities: [],
        actions: [],
      }),
    ).toBe(true);
    expect(model.generation).toBe(3);
    expect(model.revision).toBe(1);
  });

  it("correlates results to tracked request IDs", () => {
    const model = new WidgetStateModel(config);
    const id = model.trackRequest("brightness");
    expect(model.completeRequest({
      schema: 1,
      op: "result",
      room_id: config.roomId,
      panel_id: config.panelId,
      generation: 1,
      request_id: id,
      status: "accepted",
    })).toEqual({ label: "brightness", status: "accepted" });
    expect(model.completeRequest({
      schema: 1,
      op: "result",
      room_id: config.roomId,
      panel_id: config.panelId,
      generation: 1,
      request_id: crypto.randomUUID(),
      status: "accepted",
    })).toBeNull();
  });
});
