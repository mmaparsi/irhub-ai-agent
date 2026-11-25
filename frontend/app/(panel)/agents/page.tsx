"use client";

import { useAuth } from "@/components/AuthProvider";
import { Badge, Card, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { Agent } from "@/lib/types";
import Link from "next/link";
import { useEffect, useState } from "react";

export default function AgentsPage() {
  const { user } = useAuth();
  const [agents, setAgents] = useState<Agent[]>([]);

  useEffect(() => {
    api<Agent[]>("/api/agents").then(setAgents).catch(() => undefined);
  }, []);

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="عامل‌ها"
        description="هر عامل نام، پرامپت، ابزار و مدل قوی/سریع خودش را در پایگاه داده دارد."
        action={user?.role === "admin" ? <Link className="rounded-xl bg-teal-800 px-4 py-2 text-sm text-white" href="/agents/new">عامل جدید</Link> : null}
      />
      <div className="grid gap-4">
        {agents.map((agent) => (
          <Card key={agent.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold">{agent.name_fa}</h2>
                <p dir="ltr" className="text-left text-xs text-stone-500">{agent.slug}</p>
                <p className="mt-2 text-sm text-stone-600">{agent.description}</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone={agent.is_active ? "teal" : "stone"}>{agent.is_active ? "فعال" : "غیرفعال"}</Badge>
                <Badge>{agent.source === "builtin" ? "افزونه" : "پنل"}</Badge>
                {user?.role === "admin" ? (
                  <Link className="text-sm text-teal-800" href={`/agents/${agent.id}/edit`}>ویرایش</Link>
                ) : null}
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-stone-600">
              <span dir="ltr">{agent.model_strong}</span>
              <span dir="ltr">{agent.model_fast}</span>
              {agent.allowed_tools.map((tool) => (
                <Badge key={tool}>{tool}</Badge>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
