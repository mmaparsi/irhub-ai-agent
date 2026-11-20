"use client";

import { Button, Field, inputClass } from "@/components/ui";
import type { AgentInput, ToolInfo } from "@/lib/types";
import { useState } from "react";

export function AgentForm({
  initial,
  tools,
  submitLabel,
  lockSlug = false,
  onSubmit,
}: {
  initial: AgentInput;
  tools: ToolInfo[];
  submitLabel: string;
  lockSlug?: boolean;
  onSubmit: (value: AgentInput) => Promise<void>;
}) {
  const [value, setValue] = useState<AgentInput>(initial);
  const [pending, setPending] = useState(false);

  function toggleTool(name: string) {
    setValue((current) => {
      const has = current.allowed_tools.includes(name);
      return {
        ...current,
        allowed_tools: has
          ? current.allowed_tools.filter((item) => item !== name)
          : [...current.allowed_tools, name],
      };
    });
  }

  return (
    <form
      className="space-y-4"
      onSubmit={async (event) => {
        event.preventDefault();
        setPending(true);
        try {
          await onSubmit(value);
        } finally {
          setPending(false);
        }
      }}
    >
      {lockSlug ? null : (
        <Field label="شناسه انگلیسی">
          <input
            dir="ltr"
            className={inputClass}
            value={value.slug || ""}
            onChange={(event) => setValue({ ...value, slug: event.target.value })}
            required
          />
        </Field>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="نام فارسی">
          <input className={inputClass} value={value.name_fa} onChange={(event) => setValue({ ...value, name_fa: event.target.value })} required />
        </Field>
        <Field label="نام انگلیسی">
          <input dir="ltr" className={inputClass} value={value.name} onChange={(event) => setValue({ ...value, name: event.target.value })} required />
        </Field>
      </div>
      <Field label="شرح">
        <input className={inputClass} value={value.description} onChange={(event) => setValue({ ...value, description: event.target.value })} />
      </Field>
      <Field label="پرامپت سیستم">
        <textarea className={`${inputClass} min-h-36`} value={value.system_prompt} onChange={(event) => setValue({ ...value, system_prompt: event.target.value })} required />
      </Field>
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="مدل قوی">
          <input dir="ltr" className={inputClass} value={value.model_strong} onChange={(event) => setValue({ ...value, model_strong: event.target.value })} required />
        </Field>
        <Field label="مدل سریع">
          <input dir="ltr" className={inputClass} value={value.model_fast} onChange={(event) => setValue({ ...value, model_fast: event.target.value })} required />
        </Field>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="دما">
          <input
            dir="ltr"
            type="number"
            min={0}
            max={2}
            step={0.1}
            className={inputClass}
            value={value.temperature}
            onChange={(event) => setValue({ ...value, temperature: Number(event.target.value) })}
          />
        </Field>
        <label className="mt-6 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={value.is_active} onChange={(event) => setValue({ ...value, is_active: event.target.checked })} />
          فعال
        </label>
      </div>
      <fieldset>
        <legend className="mb-2 text-sm font-medium text-stone-700">ابزارهای مجاز</legend>
        <div className="grid gap-2 md:grid-cols-2">
          {tools.map((tool) => (
            <label key={tool.name} className="flex items-start gap-2 rounded-xl border border-[#e6dfd2] bg-white px-3 py-2 text-sm">
              <input type="checkbox" checked={value.allowed_tools.includes(tool.name)} onChange={() => toggleTool(tool.name)} />
              <span>
                <span dir="ltr" className="font-medium">{tool.name}</span>
                <span className="mt-0.5 block text-xs text-stone-500">{tool.description}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <Button type="submit" disabled={pending}>{pending ? "در حال ذخیره…" : submitLabel}</Button>
    </form>
  );
}
