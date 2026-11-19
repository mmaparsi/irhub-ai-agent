"use client";

import { errorText } from "@/components/AuthProvider";
import { Badge, Button, Card, ErrorNote, PageHeader } from "@/components/ui";
import { TOKEN_KEY, api, apiBase } from "@/lib/api";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

type TaskDetail = {
  id: string;
  goal: string;
  status: string;
  plan: string;
  report: string;
  step: number;
  max_steps: number;
  error: string;
  agent_name: string | null;
};

type TaskEvent = {
  seq: number;
  kind: string;
  payload: Record<string, unknown>;
};

type ArtifactRow = { id: string; filename: string; size: number };

const kindLabel: Record<string, string> = {
  plan: "برنامه",
  action: "گام",
  tool_call: "فراخوانی ابزار",
  tool_result: "نتیجه ابزار",
  report: "گزارش",
  approval: "تأیید",
  error: "خطا",
  status: "وضعیت",
};

export default function TaskDetailPage() {
  const params = useParams<{ id: string }>();
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactRow[]>([]);
  const [error, setError] = useState("");

  async function load() {
    const [detail, timeline, files] = await Promise.all([
      api<TaskDetail>(`/api/agent-tasks/${params.id}`),
      api<TaskEvent[]>(`/api/agent-tasks/${params.id}/events`),
      api<ArtifactRow[]>(`/api/agent-tasks/${params.id}/artifacts`),
    ]);
    setTask(detail);
    setEvents(timeline);
    setArtifacts(files);
  }

  useEffect(() => {
    load().catch((err) => setError(errorText(err)));
    const token = localStorage.getItem(TOKEN_KEY);
    const source = openTaskStream(`${apiBase()}/api/agent-tasks/${params.id}/stream`, token);
    return () => source.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  const status = task?.status ?? "";
  useEffect(() => {
    if (!status || ["completed", "failed", "stopped"].includes(status)) return;
    const timer = setInterval(() => {
      load().catch(() => undefined);
    }, 2000);
    return () => clearInterval(timer);
    // Poll while the run is active. `load` closes over the current route id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, params.id]);

  async function download(artifact: ArtifactRow) {
    const token = localStorage.getItem(TOKEN_KEY);
    const response = await fetch(`${apiBase()}/api/artifacts/${artifact.id}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = artifact.filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <PageHeader
        title={task?.agent_name || "وظیفه"}
        description={task?.goal}
        action={
          task && !["completed", "failed", "stopped"].includes(task.status) ? (
            <Button
              type="button"
              tone="danger"
              onClick={async () => {
                await api(`/api/agent-tasks/${params.id}/stop`, { method: "POST" });
                await load();
              }}
            >
              توقف
            </Button>
          ) : null
        }
      />
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      {task ? (
        <Card>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={task.status === "completed" ? "teal" : task.status === "failed" ? "rose" : "amber"}>{task.status}</Badge>
            <span className="text-sm text-stone-500">گام {task.step} از {task.max_steps}</span>
          </div>
          {task.plan ? <p className="mt-3 whitespace-pre-wrap text-sm leading-7">{task.plan}</p> : null}
          {task.error ? <p className="mt-3 text-sm text-rose-800">{task.error}</p> : null}
        </Card>
      ) : null}
      <div className="space-y-2">
        {events.map((event) => (
          <Card key={event.seq}>
            <p className="text-xs text-stone-500">{kindLabel[event.kind] || event.kind}</p>
            <pre className="mt-2 whitespace-pre-wrap text-sm leading-7">{formatPayload(event)}</pre>
          </Card>
        ))}
      </div>
      {task?.report ? (
        <Card>
          <h2 className="font-bold">گزارش نهایی</h2>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-7">{task.report}</p>
        </Card>
      ) : null}
      {artifacts.length ? (
        <Card>
          <h2 className="mb-2 font-bold">فایل‌ها</h2>
          <div className="flex flex-wrap gap-2">
            {artifacts.map((artifact) => (
              <Button key={artifact.id} type="button" tone="ghost" onClick={() => void download(artifact)}>
                {artifact.filename}
              </Button>
            ))}
          </div>
        </Card>
      ) : null}
    </div>
  );
}

function formatPayload(event: TaskEvent): string {
  const payload = event.payload || {};
  if (typeof payload.text === "string") return payload.text;
  if (typeof payload.content === "string") return payload.content;
  if (typeof payload.message === "string") return payload.message;
  return JSON.stringify(payload, null, 2);
}

function openTaskStream(url: string, token: string | null): { close: () => void } {
  const controller = new AbortController();
  void (async () => {
    try {
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        signal: controller.signal,
      });
      if (!response.body) return;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() || "";
        if (blocks.length) {
          window.dispatchEvent(new Event("task-progress"));
        }
      }
    } catch {
      /* closed */
    }
  })();
  return { close: () => controller.abort() };
}
