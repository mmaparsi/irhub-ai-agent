"use client";

import { AgentForm } from "@/components/AgentForm";
import { errorText, useAuth } from "@/components/AuthProvider";
import { Card, ErrorNote, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { AgentInput, ToolInfo } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const empty: AgentInput = {
  slug: "",
  name: "",
  name_fa: "",
  description: "",
  system_prompt: "",
  allowed_tools: [],
  model_strong: "",
  model_fast: "",
  temperature: 0.3,
  is_active: true,
};

export default function NewAgentPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [initial, setInitial] = useState<AgentInput>(empty);
  const [formReady, setFormReady] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (ready && user && user.role !== "admin") router.replace("/agents");
  }, [ready, router, user]);

  useEffect(() => {
    api<ToolInfo[]>("/api/tools").then(setTools).catch((err) => setError(errorText(err)));
    api<{ model_strong_default: string; model_fast_default: string }>("/api/health")
      .then((health) =>
        setInitial((current) => ({
          ...current,
          model_strong: health.model_strong_default,
          model_fast: health.model_fast_default,
        })),
      )
      .catch(() => undefined)
      .finally(() => setFormReady(true));
  }, []);

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="عامل جدید" description="از پنل ساخته می‌شود و همان اجراکنندهٔ عمومی متخصص را استفاده می‌کند." />
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      <Card>
        {formReady ? <AgentForm
          initial={initial}
          tools={tools}
          submitLabel="ساخت عامل"
          onSubmit={async (value) => {
            try {
              await api("/api/agents", { method: "POST", body: JSON.stringify(value) });
              router.push("/agents");
            } catch (err) {
              setError(errorText(err));
            }
          }}
        /> : <p className="text-sm text-stone-500">در حال بارگذاری…</p>}
      </Card>
    </div>
  );
}
