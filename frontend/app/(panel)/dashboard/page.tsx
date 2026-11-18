"use client";

import { errorText } from "@/components/AuthProvider";
import { Card, ErrorNote, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { Dashboard } from "@/lib/types";
import Link from "next/link";
import { useEffect, useState } from "react";

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Dashboard>("/api/dashboard")
      .then(setData)
      .catch((err) => setError(errorText(err)));
  }, []);

  const cards = data
    ? [
        { label: "عامل‌های فعال", value: data.agents, href: "/agents" },
        { label: "تأییدهای باز", value: data.pending_approvals, href: "/approvals" },
        { label: "سرنخ‌ها", value: data.leads, href: "/leads" },
        { label: "سندهای دانش", value: data.documents, href: "/knowledge" },
      ]
    : [];

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="داشبورد" description="نمای کوتاه از عامل‌ها، صف تأیید و داده‌های نمونه." />
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      {data?.mock_llm ? (
        <p className="mb-4 rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-950">
          حالت آزمایشی مدل روشن است. تا وقتی کلید Anthropic یا OpenAI تنظیم نشود، پاسخ گفتگو ساختگی است.
          سقف تخفیف سخت‌کد شده: {data.max_discount_percent}٪.
        </p>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <Link key={card.href} href={card.href}>
            <Card>
              <p className="text-sm text-stone-500">{card.label}</p>
              <p className="mt-2 text-3xl font-bold">{card.value}</p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
