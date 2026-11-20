export const TOKEN_KEY = "irhub_token";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) return String(item.msg);
        return "";
      })
      .filter(Boolean)
      .join("، ");
  }
  return "";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${apiBase()}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = "درخواست ناموفق بود";
    try {
      const data = (await response.json()) as { detail?: unknown };
      message = formatDetail(data.detail) || message;
    } catch {
      message = response.statusText || message;
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function streamMessage(
  conversationId: string,
  content: string,
  tier: "strong" | "fast",
  onToken: (token: string) => void,
): Promise<{ approvalIds: string[]; agentSlug?: string }> {
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${apiBase()}/api/conversations/${conversationId}/messages`, {
    method: "POST",
    headers,
    body: JSON.stringify({ content, tier }),
  });
  if (!response.ok || !response.body) {
    let message = "گفتگو ناموفق بود";
    try {
      const data = (await response.json()) as { detail?: unknown };
      message = formatDetail(data.detail) || message;
    } catch {
      /* keep the fallback */
    }
    throw new ApiError(response.status, message);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let approvalIds: string[] = [];
  let agentSlug: string | undefined;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const line = block.split("\n").find((item) => item.startsWith("data:"));
      if (!line) continue;
      const payload = JSON.parse(line.slice(5).trim()) as {
        token?: string;
        error?: string;
        done?: boolean;
        approval_ids?: string[];
        agent_slug?: string;
      };
      if (payload.error) throw new ApiError(500, payload.error);
      if (payload.token) onToken(payload.token);
      if (payload.done) {
        approvalIds = payload.approval_ids || [];
        agentSlug = payload.agent_slug;
      }
    }
  }
  return { approvalIds, agentSlug };
}
