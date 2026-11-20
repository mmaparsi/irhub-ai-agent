"use client";

import { Badge, Button, Card, Empty, PageHeader, inputClass } from "@/components/ui";
import { TOKEN_KEY, api, apiBase } from "@/lib/api";
import { leadStatus, partyLabel } from "@/lib/labels";
import type { Lead } from "@/lib/types";
import { useEffect, useState } from "react";

const tone: Record<string, "stone" | "teal" | "amber"> = {
  new: "stone",
  qualified: "teal",
  negotiating: "amber",
};

export default function LeadsPage() {
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [party, setParty] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Lead | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams();
    if (party) params.set("party", party);
    if (status) params.set("status", status);
    if (q.trim()) params.set("q", q.trim());
    const query = params.toString();
    api<Lead[]>(`/api/leads${query ? `?${query}` : ""}`)
      .then((rows) => {
        setLeads(rows);
        setError("");
      })
      .catch(() => setError("فهرست سرنخ‌ها بارگذاری نشد."));
  }, [party, status, q]);

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="سرنخ‌ها"
        description="مشتری‌ها برای فروش و تأمین‌کننده‌ها برای جذب. هر نقش فقط پروندهٔ خودش را می‌بیند."
        action={
          <Button
            type="button"
            onClick={async () => {
              const token = localStorage.getItem(TOKEN_KEY);
              const response = await fetch(`${apiBase()}/api/leads/export.csv`, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
              });
              const blob = await response.blob();
              const url = URL.createObjectURL(blob);
              const link = document.createElement("a");
              link.href = url;
              link.download = "leads.csv";
              link.click();
              URL.revokeObjectURL(url);
            }}
          >
            خروجی CSV
          </Button>
        }
      />
      <div className="mb-4 grid gap-2 md:grid-cols-3">
        <input className={inputClass} placeholder="جست‌وجو" value={q} onChange={(event) => setQ(event.target.value)} />
        <select className={inputClass} value={party} onChange={(event) => setParty(event.target.value)}>
          <option value="">همهٔ انواع</option>
          <option value="customer">مشتری</option>
          <option value="supplier">تأمین‌کننده</option>
        </select>
        <select className={inputClass} value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">همهٔ وضعیت‌ها</option>
          {Object.entries(leadStatus).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
      </div>
      {error ? <p className="mb-3 text-sm text-rose-800">{error}</p> : null}
      {leads === null ? <p className="text-sm text-stone-500">در حال بارگذاری…</p> : null}
      {leads && leads.length === 0 ? <Empty>سرنخی با این فیلتر پیدا نشد.</Empty> : null}
      <div className="overflow-hidden rounded-2xl border border-[#e6dfd2] bg-white">
        <table className="w-full text-sm">
          <thead className="bg-stone-50 text-stone-500">
            <tr>
              <th className="px-3 py-2 text-right font-medium">عنوان</th>
              <th className="px-3 py-2 text-right font-medium">نوع</th>
              <th className="px-3 py-2 text-right font-medium">شرکت</th>
              <th className="px-3 py-2 text-right font-medium">منبع</th>
              <th className="px-3 py-2 text-right font-medium">وضعیت</th>
            </tr>
          </thead>
          <tbody>
            {leads?.map((lead) => (
              <tr key={lead.id} className="cursor-pointer border-t border-[#efe8dc] hover:bg-teal-50" onClick={() => setSelected(lead)}>
                <td className="px-3 py-3 font-medium">{lead.title}</td>
                <td className="px-3 py-3">{partyLabel[lead.party || "customer"] || lead.party}</td>
                <td className="px-3 py-3">{lead.company_name}</td>
                <td className="px-3 py-3">{lead.source}</td>
                <td className="px-3 py-3">
                  <Badge tone={tone[lead.status] || "stone"}>{leadStatus[lead.status] || lead.status}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected ? (
        <div className="fixed inset-y-0 left-0 z-20 w-full max-w-md overflow-y-auto border-r border-[#e6dfd2] bg-[#fffcf7] p-5 shadow-xl">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold">{selected.title}</h2>
              <p className="text-sm text-stone-500">{selected.company_name} · {selected.city}</p>
            </div>
            <button className="text-sm text-stone-500" onClick={() => setSelected(null)} type="button">بستن</button>
          </div>
          <Card>
            <p className="text-sm">نوع: {partyLabel[selected.party || "customer"]}</p>
            <p className="mt-1 text-sm">منبع: {selected.source || "—"}</p>
            <p className="mt-1 text-sm">وب‌سایت: {selected.website || "—"}</p>
            <p className="mt-1 text-sm">امتیاز: {selected.score}</p>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-7">{selected.notes || "یادداشتی نیست."}</p>
            <ul className="mt-3 space-y-1 text-sm">
              {selected.contacts.map((contact) => (
                <li key={`${contact.email}-${contact.phone}`}>
                  {contact.name} {contact.title ? `· ${contact.title}` : ""}
                  <span dir="ltr" className="ms-2 text-stone-500">{contact.email || contact.phone}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
