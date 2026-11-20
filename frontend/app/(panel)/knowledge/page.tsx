"use client";

import { errorText, useAuth } from "@/components/AuthProvider";
import { Badge, Button, Card, ErrorNote, Field, PageHeader, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import type { KnowledgeDoc } from "@/lib/types";
import { useEffect, useState } from "react";

export default function KnowledgePage() {
  const { user } = useAuth();
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [error, setError] = useState("");
  const canUpload = user?.role === "admin" || user?.role === "sales" || user?.role === "supplier_acquisition";

  function load() {
    return api<KnowledgeDoc[]>("/api/knowledge").then(setDocs);
  }

  useEffect(() => {
    load().catch((err) => setError(errorText(err)));
  }, []);

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <PageHeader title="پایگاه دانش" description="متن سند ذخیره می‌شود و یک بردار برای جست‌وجوی pgvector ساخته می‌شود." />
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      {canUpload ? (
        <Card>
          <form
            className="space-y-3"
            onSubmit={async (event) => {
              event.preventDefault();
              setError("");
              try {
                await api("/api/knowledge", {
                  method: "POST",
                  body: JSON.stringify({ title, content, source: "upload" }),
                });
                setTitle("");
                setContent("");
                await load();
              } catch (err) {
                setError(errorText(err));
              }
            }}
          >
            <Field label="عنوان">
              <input className={inputClass} value={title} onChange={(event) => setTitle(event.target.value)} required />
            </Field>
            <Field label="متن یا فایل txt/md">
              <input
                type="file"
                accept=".txt,.md,.markdown,text/plain"
                className="mb-2 block text-sm"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  setContent(await file.text());
                  if (!title) setTitle(file.name.replace(/\.[^.]+$/, ""));
                }}
              />
              <textarea className={`${inputClass} min-h-32`} value={content} onChange={(event) => setContent(event.target.value)} required />
            </Field>
            <Button type="submit">بارگذاری</Button>
          </form>
        </Card>
      ) : null}
      <div className="space-y-3">
        {docs.map((doc) => (
          <Card key={doc.id}>
            <div className="flex items-center justify-between gap-2">
              <h2 className="font-bold">{doc.title}</h2>
              <Badge tone={doc.status === "ready" ? "teal" : "amber"}>{doc.status === "ready" ? "آماده" : doc.status}</Badge>
            </div>
            <p className="mt-2 text-sm text-stone-600">{doc.excerpt}</p>
          </Card>
        ))}
        {docs.length === 0 ? <p className="text-sm text-stone-500">هنوز سندی بارگذاری نشده است.</p> : null}
      </div>
    </div>
  );
}
