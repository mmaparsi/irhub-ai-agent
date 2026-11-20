"use client";

import { errorText, useAuth } from "@/components/AuthProvider";
import { Badge, Button, Card, Empty, ErrorNote, PageHeader, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type Channel = {
  channel: string;
  label: string;
  configured: boolean;
  mode: "approval" | "auto";
  daily_limit: number;
  sent_today: number;
};

export default function ChannelsPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [rows, setRows] = useState<Channel[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (ready && user && user.role !== "admin") router.replace("/dashboard");
  }, [ready, router, user]);

  function load() {
    return api<Channel[]>("/api/channels").then(setRows);
  }

  useEffect(() => {
    if (user?.role === "admin") load().catch((err) => setError(errorText(err)));
  }, [user]);

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <PageHeader
        title="کانال‌های ارتباط"
        description="رمزها فقط در محیط سرور می‌مانند. اینجا فقط وضعیت و سیاست ارسال دیده می‌شود."
      />
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      {rows === null ? <p className="text-sm text-stone-500">در حال بارگذاری…</p> : null}
      {rows && rows.length === 0 ? <Empty>کانالی تعریف نشده است.</Empty> : null}
      {rows?.map((row) => (
        <Card key={row.channel}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-bold">{row.label}</h2>
              <p className="text-sm text-stone-500">امروز {row.sent_today} از {row.daily_limit}</p>
            </div>
            <Badge tone={row.configured ? "teal" : "stone"}>{row.configured ? "آماده" : "تنظیم نشده"}</Badge>
          </div>
          <form
            className="mt-3 grid gap-2 md:grid-cols-[1fr_8rem_auto]"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              setError("");
              try {
                await api(`/api/channels/${row.channel}`, {
                  method: "PATCH",
                  body: JSON.stringify({
                    mode: String(form.get("mode")),
                    daily_limit: Number(form.get("daily_limit")),
                  }),
                });
                await load();
              } catch (err) {
                setError(errorText(err));
              }
            }}
          >
            <select className={inputClass} name="mode" defaultValue={row.mode}>
              <option value="approval">نیاز به تأیید</option>
              <option value="auto">ارسال خودکار</option>
            </select>
            <input className={inputClass} name="daily_limit" type="number" min={0} max={500} defaultValue={row.daily_limit} />
            <Button type="submit">ذخیره</Button>
          </form>
        </Card>
      ))}
    </div>
  );
}
