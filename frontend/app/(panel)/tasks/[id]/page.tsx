"use client";

import { errorText } from "@/components/AuthProvider";
import { Badge, Button, Card, Empty, ErrorNote, PageHeader } from "@/components/ui";
import { TOKEN_KEY, api, apiBase } from "@/lib/api";
import { taskStatus } from "@/lib/labels";
import { live, type LiveMessage } from "@/lib/live";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

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
  created_at?: string;
};

type ArtifactRow = { id: string; filename: string; size: number };

const kindLabel: Record<string, string> = {
  plan: "برنامه",
  action: "گام",
  step_start: "شروع گام",
  step_end: "پایان گام",
  token: "متن مدل",
  tool_call: "فراخوانی ابزار",
  tool_result: "نتیجه ابزار",
  tool_progress: "پیشرفت ابزار",
  report: "گزارش",
  approval: "تأیید",
  error: "خطا",
  status: "وضعیت",
  retry: "تلاش دوباره",
  model_switch: "تعویض مدل",
  lead: "سرنخ",
};

export default function TaskDetailPage() {
  const params = useParams<{ id: string }>();
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactRow[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

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
    setLoading(true);
    load()
      .catch((err) => setError(errorText(err)))
      .finally(() => setLoading(false));
    live.subscribeTask(params.id, 0);
    const stop = live.on((message: LiveMessage) => {
      if (message.type !== "task" || message.task_id !== params.id || message.seq == null || !message.kind) return;
      setEvents((current) => {
        if (current.some((item) => item.seq === message.seq)) return current;
        return [...current, { seq: message.seq as number, kind: message.kind as string, payload: message.payload || {}, created_at: message.created_at }].sort((a, b) => a.seq - b.seq);
      });
      if (message.kind === "status" || message.kind === "report" || message.kind === "error") {
        load().catch(() => undefined);
      }
    });
    return () => {
      stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  const rows = useMemo(() => groupEvents(events), [events]);
  const status = task?.status ?? "";

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
        title={task?.agent_name || "فضای وظیفه"}
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
      {loading && !task ? <p className="text-sm text-stone-500">در حال بارگذاری خط زمان…</p> : null}
      {task ? (
        <Card>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={task.status === "completed" ? "teal" : task.status === "failed" ? "rose" : "amber"}>
              {taskStatus[status] || status}
            </Badge>
            <span className="text-sm text-stone-500">گام {task.step} از {task.max_steps}</span>
          </div>
          {task.plan ? <p className="mt-3 whitespace-pre-wrap text-sm leading-7">{task.plan}</p> : null}
          {task.error ? <p className="mt-3 text-sm text-rose-800">{task.error}</p> : null}
        </Card>
      ) : null}
      {rows.length === 0 && !loading ? <Empty>هنوز رویدادی ثبت نشده است.</Empty> : null}
      <div className="space-y-2">
        {rows.map((row) => (
          <Card key={row.key}>
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-stone-500">{kindLabel[row.kind] || row.kind}</p>
              {row.at ? <time className="text-xs text-stone-400">{new Date(row.at).toLocaleTimeString("fa-IR")}</time> : null}
            </div>
            {row.kind === "tool_call" || row.kind === "tool_result" ? (
              <details className="mt-2">
                <summary className="cursor-pointer text-sm font-medium">{summary(row)}</summary>
                <pre className="mt-2 whitespace-pre-wrap text-sm leading-7">{row.text}</pre>
              </details>
            ) : (
              <p className="mt-2 whitespace-pre-wrap text-sm leading-7">{row.text}</p>
            )}
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

function summary(row: { kind: string; text: string }) {
  const line = row.text.split("\n")[0] || row.kind;
  return line.slice(0, 120);
}

function groupEvents(events: TaskEvent[]) {
  const rows: { key: string; kind: string; text: string; at?: string }[] = [];
  let token: { key: string; kind: string; text: string; at?: string } | null = null;
  for (const event of events) {
    if (event.kind === "token") {
      const text = String(event.payload.text || "");
      if (token) token.text += text;
      else {
        token = { key: `t-${event.seq}`, kind: "token", text, at: event.created_at };
        rows.push(token);
      }
      continue;
    }
    token = null;
    rows.push({
      key: String(event.seq),
      kind: event.kind,
      text: formatPayload(event),
      at: event.created_at,
    });
  }
  return rows;
}

function formatPayload(event: TaskEvent): string {
  const payload = event.payload || {};
  if (typeof payload.text === "string") return payload.text;
  if (typeof payload.content === "string") return payload.content;
  if (typeof payload.message === "string") return payload.message;
  if (typeof payload.status === "string" && Object.keys(payload).length === 1) return taskStatus[payload.status] || payload.status;
  return JSON.stringify(payload, null, 2);
}
