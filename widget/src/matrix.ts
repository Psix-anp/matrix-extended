import {
  WidgetApi,
  WidgetApiToWidgetAction,
  type ISendToDeviceToWidgetActionRequest,
} from "matrix-widget-api";

import {
  WIDGET_EVENT_TYPE,
  WIDGET_RECEIVE_CAPABILITY,
  WIDGET_SEND_CAPABILITY,
  isWidgetInboundMessage,
  type WidgetConfig,
  type WidgetInboundMessage,
  type WidgetRequest,
} from "./protocol";

export type BridgeStatus = "idle" | "ready" | "denied" | "error";

type MessageHandler = (message: WidgetInboundMessage) => void;
type StatusHandler = (status: BridgeStatus, detail?: string) => void;

export interface WidgetApiAdapter {
  requestCapabilityToSendToDevice(eventType: string): void;
  requestCapabilityToReceiveToDevice(eventType: string): void;
  hasCapability(capability: string): boolean;
  on(event: string, handler: (...args: any[]) => void): unknown;
  start(): void;
  sendContentLoaded(): Promise<void>;
  sendToDevice(
    eventType: string,
    encrypted: boolean,
    contentMap: Record<string, Record<string, object>>,
  ): Promise<unknown>;
  transport: { reply(request: unknown, response: object): void };
}

export class MatrixWidgetBridge {
  public status: BridgeStatus = "idle";

  private readonly messageHandlers = new Set<MessageHandler>();
  private readonly statusHandlers = new Set<StatusHandler>();

  public constructor(
    public readonly config: WidgetConfig,
    private readonly api: WidgetApiAdapter = new WidgetApi(config.widgetId, null),
  ) {}

  public onMessage(handler: MessageHandler): () => void {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  public onStatus(handler: StatusHandler): () => void {
    this.statusHandlers.add(handler);
    return () => this.statusHandlers.delete(handler);
  }

  private setStatus(status: BridgeStatus, detail?: string): void {
    this.status = status;
    for (const handler of this.statusHandlers) handler(status, detail);
  }

  public start(): void {
    this.api.requestCapabilityToSendToDevice(WIDGET_EVENT_TYPE);
    this.api.requestCapabilityToReceiveToDevice(WIDGET_EVENT_TYPE);

    this.api.on(`action:${WidgetApiToWidgetAction.SendToDevice}`, (...args: any[]) => {
      const event = args[0] as CustomEvent<ISendToDeviceToWidgetActionRequest> | undefined;
      if (!event?.detail) return;
      event.preventDefault?.();
      const data = event.detail.data;
      try {
        if (
          data.type === WIDGET_EVENT_TYPE &&
          data.sender === this.config.integrationUserId &&
          isWidgetInboundMessage(data.content)
        ) {
          for (const handler of this.messageHandlers) handler(data.content);
        }
      } finally {
        this.api.transport.reply(event.detail, {});
      }
    });

    this.api.on("ready", () => {
      const granted =
        this.api.hasCapability(WIDGET_SEND_CAPABILITY) &&
        this.api.hasCapability(WIDGET_RECEIVE_CAPABILITY);
      if (!granted) {
        this.setStatus("denied", "required_capability_not_granted");
        return;
      }
      this.setStatus("ready");
      void this.api.sendContentLoaded().catch((error: unknown) => {
        this.setStatus("error", String(error));
      });
    });

    this.api.on("error:preparing", (error: unknown) => {
      this.setStatus("error", String(error));
    });
    this.api.start();
  }

  public async send(content: WidgetRequest): Promise<void> {
    if (this.status !== "ready") {
      throw new Error("Widget Matrix capabilities are not ready");
    }
    await this.api.sendToDevice(WIDGET_EVENT_TYPE, true, {
      [this.config.integrationUserId]: {
        [this.config.integrationDeviceId]: content,
      },
    });
  }
}
