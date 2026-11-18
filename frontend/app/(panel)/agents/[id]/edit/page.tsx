"use client";

import { AgentForm } from "@/components/AgentForm";
import { errorText, useAuth } from "@/components/AuthProvider";
import { Card, ErrorNote, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { Agent, AgentInput, ToolInfo } from "@/lib/types";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function EditAgentPage() {
  const params = useParams<{ id: string }>();
  const { user, ready } = useAuth();
  const router = useRouter();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (ready && user && user.role !== "admin") router.replace("/agents");
  }, [ready, router, user]);

  useEffect(() => {
    api<Agent>(`/api/agents/${params.id}`).then(setAgent).catch((err) => setError(errorText(err)));
    api<ToolInfo[]>("/api/tools").then(setTools).catch((err) => setError(errorText(err)));
  }, [params.id]);

  const initial: AgentInput | null = agent
    ? {
        name: agent.name,
        name_fa: agent.name_fa,
        description: agent.description,
        system_prompt: agent.system_prompt,
        allowed_tools: agent.allowed_tools,
        model_strong: agent.model_strong,
        model_fast: agent.model_fast,
        temperature: agent.temperature,
        is_active: agent.is_active,
      }
    : null;

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="ویرایش عامل" description={agent ? agent.name_fa : ""} />
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      {initial ? (
        <Card>
          <p dir="ltr" className="mb-4 text-left text-xs text-stone-500">{agent?.slug}</p>
          <AgentForm
            initial={initial}
            tools={tools}
            lockSlug
            submitLabel="ذخیره"
            onSubmit={async (value) => {
              try {
                await api(`/api/agents/${params.id}`, { method: "PATCH", body: JSON.stringify(value) });
                router.push("/agents");
              } catch (err) {
                setError(errorText(err));
              }
            }}
          />
        </Card>
      ) : null}
    </div>
  );
}
