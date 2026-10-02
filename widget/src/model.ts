import type {
  PanelSnapshot,
  WidgetConfig,
  WidgetInboundMessage,
  WidgetResult,
} from "./protocol";

interface PendingRequest {
  label: string;
  createdAt: number;
}

export class WidgetStateModel {
  public snapshot: PanelSnapshot | null = null;
  public generation = 0;
  public revision = 0;
  public connected = false;
  public lastError: string | null = null;

  private readonly pending = new Map<string, PendingRequest>();

  public constructor(public readonly config: WidgetConfig) {}

  public accept(message: WidgetInboundMessage): boolean {
    if (message.room_id !== this.config.roomId || message.panel_id !== this.config.panelId) {
      return false;
    }
    if (message.op !== "state") return false;
    if (!Number.isInteger(message.revision) || message.revision < 1) return false;
    if (message.generation < this.generation) return false;
    if (message.generation === this.generation && message.revision <= this.revision) return false;

    this.generation = message.generation;
    this.revision = message.revision;
    this.snapshot = message;
    this.connected = true;
    this.lastError = null;
    return true;
  }

  public trackRequest(label: string): string {
    const id = crypto.randomUUID();
    this.trackRequestWithId(id, label);
    return id;
  }

  public trackRequestWithId(requestId: string, label: string): void {
    this.pending.set(requestId, { label, createdAt: Date.now() });
    if (this.pending.size > 128) {
      const oldest = [...this.pending.entries()].sort(
        (a, b) => a[1].createdAt - b[1].createdAt,
      )[0];
      if (oldest) this.pending.delete(oldest[0]);
    }
  }

  public completeRequest(message: WidgetResult): { label: string; status: string } | null {
    const requestId = message.request_id;
    if (!requestId) return null;
    const pending = this.pending.get(requestId);
    if (!pending) return null;
    this.pending.delete(requestId);
    return { label: pending.label, status: message.status };
  }

  public handleError(message: WidgetInboundMessage): void {
    if (message.op !== "error") return;
    this.lastError = message.error || message.status;
    if (["stale_generation", "needs_repair", "widget_disabled"].includes(message.status)) {
      this.connected = false;
    }
  }
}
