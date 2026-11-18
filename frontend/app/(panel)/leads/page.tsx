"use client";

import { Badge, Card, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { leadStatus } from "@/lib/labels";
import type { Lead } from "@/lib/types";
import { useEffect, useState } from "react";

const tone: Record<string, "stone" | "teal" | "amber"> = {
  new: "stone",
  qualified: "teal",
  negotiating: "amber",
};

export default function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);

  useEffect(() => {
    api<Lead[]>("/api/leads").then(setLeads).catch(() => undefined);
  }, []);

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="سرنخ‌ها" description="نمونه‌های اولیه برای مشتری‌یابی. اتصال CRM هنوز ساخته نشده است." />
      <div className="space-y-3">
        {leads.map((lead) => (
          <Card key={lead.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-bold">{lead.title}</h2>
                <p className="text-sm text-stone-600">
                  {lead.company_name} · {lead.city} · {lead.industry}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone={tone[lead.status] || "stone"}>{leadStatus[lead.status] || lead.status}</Badge>
                <span className="text-sm text-stone-500">امتیاز {lead.score}</span>
              </div>
            </div>
            <p className="mt-2 text-sm text-stone-600">{lead.notes}</p>
            {lead.contacts.length ? (
              <ul className="mt-3 space-y-1 text-sm">
                {lead.contacts.map((contact) => (
                  <li key={contact.email}>
                    {contact.name}، {contact.title}
                    <span dir="ltr" className="ms-2 text-stone-500">{contact.email}</span>
                  </li>
                ))}
              </ul>
            ) : null}
            {lead.deals.map((deal) => (
              <p key={deal.title} className="mt-2 text-sm">
                {deal.title}: {new Intl.NumberFormat("fa-IR").format(deal.value)} {deal.currency}
                <span className="text-stone-500"> · تخفیف {deal.discount_percent}٪</span>
              </p>
            ))}
          </Card>
        ))}
      </div>
    </div>
  );
}
