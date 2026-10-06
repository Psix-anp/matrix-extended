import { describe, expect, it, vi } from "vitest";

import { MatrixWidgetBridge, type WidgetApiAdapter } from "../src/matrix";
import {
  WIDGET_EVENT_TYPE,
  WIDGET_RECEIVE_CAPABILITY,
  WIDGET_SEND_CAPABILITY,
  buildSubscribe,
  type WidgetConfig,
} from "../src/protocol";

const config: WidgetConfig = {
  roomId: "!room:example.org",
  panelId: "living",
  widgetId: "widget-1",
  integrationUserId: "@ha:example.org",
  integrationDeviceId: "HADEVICE",
};

class FakeApi implements WidgetApiAdapter {
  public requestedSend: string[] = [];
  public requestedReceive: string[] = [];
  public handlers = new Map<string, (...args: any[]) => void>();
  public granted = new Set<string>([WIDGET_SEND_CAPABILITY, WIDGET_RECEIVE_CAPABILITY]);
  public sendToDevice = vi.fn(async () => ({}));
  public sendContentLoaded = vi.fn(async () => undefined);
  public transport = { reply: vi.fn() };

  requestCapabilityToSendToDevice(type: string): void { this.requestedSend.push(type); }
  requestCapabilityToReceiveToDevice(type: string): void { this.requestedReceive.push(type); }
  hasCapability(capability: string): boolean { return this.granted.has(capability); }
  on(event: string, handler: (...args: any[]) => void): unknown { this.handlers.set(event, handler); return this; }
  start(): void {}
  emit(event: string, value?: unknown): void { this.handlers.get(event)?.(value); }
}

describe("MatrixWidgetBridge", () => {
  it("requests only the widget to-device capabilities", () => {
    const api = new FakeApi();
    new MatrixWidgetBridge(config, api).start();
    expect(api.requestedSend).toEqual([WIDGET_EVENT_TYPE]);
    expect(api.requestedReceive).toEqual([WIDGET_EVENT_TYPE]);
  });

  it("targets the exact integration device and requests encrypted sending", async () => {
    const api = new FakeApi();
    const bridge = new MatrixWidgetBridge(config, api);
    bridge.start();
    api.emit("ready");
    await bridge.send(buildSubscribe(config));

    expect(api.sendToDevice).toHaveBeenCalledTimes(1);
    expect(api.sendToDevice).toHaveBeenCalledWith(
      WIDGET_EVENT_TYPE,
      true,
      {
        "@ha:example.org": {
          HADEVICE: buildSubscribe(config),
        },
      },
    );
    expect(JSON.stringify(api.sendToDevice.mock.calls)).not.toContain('"*"');
  });

  it("fails closed when the receive capability is denied", () => {
    const api = new FakeApi();
    api.granted.delete(WIDGET_RECEIVE_CAPABILITY);
    const bridge = new MatrixWidgetBridge(config, api);
    bridge.start();
    api.emit("ready");
    expect(bridge.status).toBe("denied");
  });
});
