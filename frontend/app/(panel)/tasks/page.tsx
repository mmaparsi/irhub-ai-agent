"use client";

import { Badge, Card, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import Link from "next/link";
import { useEffect, useState } from "react";

type TaskRow = {
  id: string;
  goal: string;
  status: string;
  agent_name: string | null;
  step: number;
  max_steps: number;
  updated_at: string;
};

const label: Record<string, string> = {
  queued: "در صف",
  running: "در حال اجرا",
  waiting_approval: "منتظر تأیید",
  stopping: "در حال توقف",
  stopped: "متوقف",
  completed: "تمام‌شده",
  failed: "ناموفق",
};

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskRow[]>([]);

  useEffect(() => {
    api<TaskRow[]>("/api/agent-tasks").then(setTasks).catch(() => undefined);
  }, []);

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="وظیفه‌ها"
        description="عامل خودش برنامه می‌ریزد، ابزار را صدا می‌زند و گزارش را بعداً تحویل می‌دهد."
        action={<Link className="rounded-xl bg-teal-800 px-4 py-2 text-sm text-white" href="/tasks/new">وظیفه جدید</Link>}
      />
      <div className="space-y-3">
        {tasks.map((task) => (
          <Link key={task.id} href={`/tasks/${task.id}`}>
            <Card>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-bold">{task.goal}</h2>
                  <p className="text-sm text-stone-500">{task.agent_name || "عامل"} · گام {task.step} از {task.max_steps}</p>
                </div>
                <Badge tone={task.status === "completed" ? "teal" : task.status === "failed" ? "rose" : "amber"}>
                  {label[task.status] || task.status}
                </Badge>
              </div>
            </Card>
          </Link>
        ))}
        {tasks.length === 0 ? <p className="text-sm text-stone-500">هنوز وظیفه‌ای ثبت نشده است.</p> : null}
      </div>
    </div>
  );
}
