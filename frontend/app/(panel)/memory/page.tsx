"use client";

import { errorText } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, PageHeader, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";

type MemoryRow = {
  id: string;
  agent_type: string;
  entity_type: string;
  entity_id: string | null;
  content: string;
  importance: number;
  created_at: string;
};

export default function MemoryPage() {
  const [rows, setRows] = useState<MemoryRow[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  function load(q = query) {
    const path = q.trim() ? `/api/memories?q=${encodeURIComponent(q.trim())}` : "/api/memories";
    return api<MemoryRow[]>(path).then(setRows);
  }

  useEffect(() => {
    api<MemoryRow[]>("/api/memories")
      .then(setRows)
      .catch((err) => setError(errorText(err)));
  }, []);

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <PageHeader
        title="حافظه"
        description="واقعیت‌های ماندگار عامل‌ها. نقش شما فقط حافظهٔ عامل‌های خودش را می‌بیند."
      />
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      <Card>
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            load().catch((err) => setError(errorText(err)));
          }}
        >
          <input
            className={inputClass}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="جست‌وجو در حافظه"
          />
          <Button type="submit">جست‌وجو</Button>
        </form>
      </Card>
      <div className="space-y-2">
        {rows.map((row) => (
          <Card key={row.id}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs text-stone-500">
                  {row.agent_type || "عمومی"} · {row.entity_type}
                  {row.entity_id ? ` · ${row.entity_id}` : ""} · اهمیت {row.importance}
                </p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-7">{row.content}</p>
              </div>
              <Button
                type="button"
                onClick={() => {
                  api(`/api/memories/${row.id}`, { method: "DELETE" })
                    .then(() => load())
                    .catch((err) => setError(errorText(err)));
                }}
              >
                حذف
              </Button>
            </div>
          </Card>
        ))}
        {rows.length === 0 ? <p className="text-sm text-stone-500">حافظه‌ای نیست.</p> : null}
      </div>
    </div>
  );
}
