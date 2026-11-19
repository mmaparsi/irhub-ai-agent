"use client";

import { errorText, useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, Field, PageHeader, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import type { Agent } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function NewTaskPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentId, setAgentId] = useState("");
  const [goal, setGoal] = useState("۳۰ تولیدکننده مبلمان در تهران را با اطلاعات تماس پیدا کن، در سرنخ‌ها ثبت کن و رتبه‌بندی کن");
  const [maxSteps, setMaxSteps] = useState(12);
  const [error, setError] = useState("");
  const canSend = user?.role === "admin" || user?.role === "expert";

  useEffect(() => {
    api<Agent[]>("/api/agents")
      .then((rows) => {
        const active = rows.filter((item) => item.is_active);
        setAgents(active);
        const lead = active.find((item) => item.slug === "lead_generation");
        setAgentId((lead || active[0])?.id || "");
      })
      .catch((err) => setError(errorText(err)));
  }, []);

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="وظیفه جدید" description="هدف را بنویسید. اجرا در پس‌زمینه ادامه پیدا می‌کند و می‌توانید بعداً برگردید." />
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      <Card>
        <form
          className="space-y-4"
          onSubmit={async (event) => {
            event.preventDefault();
            setError("");
            try {
              const task = await api<{ id: string }>("/api/agent-tasks", {
                method: "POST",
                body: JSON.stringify({ agent_id: agentId, goal, max_steps: maxSteps }),
              });
              router.push(`/tasks/${task.id}`);
            } catch (err) {
              setError(errorText(err));
            }
          }}
        >
          <Field label="عامل">
            <select className={inputClass} value={agentId} onChange={(event) => setAgentId(event.target.value)}>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>{agent.name_fa}</option>
              ))}
            </select>
          </Field>
          <Field label="هدف">
            <textarea className={`${inputClass} min-h-32`} value={goal} onChange={(event) => setGoal(event.target.value)} required />
          </Field>
          <Field label="سقف گام">
            <input dir="ltr" type="number" min={1} max={30} className={inputClass} value={maxSteps} onChange={(event) => setMaxSteps(Number(event.target.value))} />
          </Field>
          <Button type="submit" disabled={!canSend || !agentId}>شروع اجرا</Button>
        </form>
      </Card>
    </div>
  );
}
