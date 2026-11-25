import { TOKEN_KEY, apiBase } from "@/lib/api";

export type LiveMessage = {
  type: string;
  seq?: number;
  kind?: string;
  payload?: Record<string, unknown>;
  task_id?: string;
  last_seq?: number;
  detail?: string;
  created_at?: string;
};

type Handler = (message: LiveMessage) => void;

class LiveClient {
  private socket: WebSocket | null = null;
  private handlers = new Set<Handler>();
  private pending: object[] = [];
  private retry = 1000;
  private token = "";
  private closed = true;

  connect(token: string) {
    this.token = token;
    this.closed = false;
    this.open();
  }

  disconnect() {
    this.closed = true;
    this.socket?.close();
    this.socket = null;
  }

  on(handler: Handler) {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  send(message: object) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
      return;
    }
    this.pending.push(message);
  }

  subscribeTask(taskId: string, afterSeq: number) {
    this.send({ action: "subscribe", task_id: taskId, after_seq: afterSeq });
  }

  private open() {
    if (this.closed || !this.token) return;
    const base = apiBase().replace(/^http/, "ws");
    const socket = new WebSocket(`${base}/api/ws?token=${encodeURIComponent(this.token)}`);
    this.socket = socket;
    socket.onopen = () => {
      this.retry = 1000;
      socket.send(JSON.stringify({ action: "inbox", after_seq: 0 }));
      for (const message of this.pending) socket.send(JSON.stringify(message));
      this.pending = [];
    };
    socket.onmessage = (event) => {
      const message = JSON.parse(String(event.data)) as LiveMessage;
      for (const handler of this.handlers) handler(message);
      if (message.type === "activity" || message.type === "task") {
        window.dispatchEvent(new Event("irhub-live"));
      }
    };
    socket.onclose = () => {
      if (this.closed) return;
      window.setTimeout(() => this.open(), this.retry);
      this.retry = Math.min(this.retry * 2, 15000);
    };
  }
}

export const live = new LiveClient();

export function currentToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}
