"use client";

import { errorText, useAuth } from "@/components/AuthProvider";
import { Badge, Button, Card, ErrorNote, Field, PageHeader, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { actionLabel, approvalStatus, executionStatus } from "@/lib/labels";
import type { Approval } from "@/lib/types";
import { useEffect, useState } from "react";

type ActionType = "email" | "message" | "price_offer";

export default function ApprovalsPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState<Approval[]>([]);
  const [error, setError] = useState("");
  const [cap, setCap] = useState<number | null>(null);
  const [actionType, setActionType] = useState<ActionType>("price_offer");
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [dealTitle, setDealTitle] = useState("");
  const [amount, setAmount] = useState("0");
  const [discount, setDiscount] = useState("10");
  const canAct = user?.role === "admin" || user?.role === "sales" || user?.role === "supplier_acquisition";

  async function load() {
    const [list, health] = await Promise.all([
      api<Approval[]>("/api/approvals"),
      api<{ max_discount_percent: number }>("/api/health"),
    ]);
    setRows(list);
    setCap(health.max_discount_percent);
  }

  useEffect(() => {
    load().catch((err) => setError(errorText(err)));
  }, []);

  async function decide(id: string, decision: "approved" | "rejected") {
    setError("");
    try {
      await api(`/api/approvals/${id}/decide`, {
        method: "POST",
        body: JSON.stringify({ decision, note: "" }),
      });
      await load();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function createRequest() {
    setError("");
    const payload =
      actionType === "price_offer"
        ? {
            deal_title: dealTitle,
            amount: Number(amount),
            currency: "IRR",
            discount_percent: Number(discount),
            note: body,
          }
        : actionType === "email"
          ? { to, subject, body }
          : { channel: "message", to, body };
    try {
      await api("/api/approvals", { method: "POST", body: JSON.stringify({ action_type: actionType, payload }) });
      setBody("");
      await load();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <PageHeader
        title="صف تأیید"
        description={cap === null ? "اقدام خروجی تا تأیید کارشناس اجرا نمی‌شود." : `سقف تخفیف در کد: ${cap}٪. بالاتر از آن حتی ثبت نمی‌شود.`}
      />
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      {canAct ? (
        <Card>
          <h2 className="mb-3 font-bold">درخواست جدید</h2>
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="نوع">
              <select className={inputClass} value={actionType} onChange={(event) => setActionType(event.target.value as ActionType)}>
                <option value="price_offer">پیشنهاد قیمت</option>
                <option value="email">ایمیل</option>
                <option value="message">پیام</option>
              </select>
            </Field>
            {actionType === "price_offer" ? (
              <>
                <Field label="عنوان">
                  <input className={inputClass} value={dealTitle} onChange={(event) => setDealTitle(event.target.value)} />
                </Field>
                <Field label="مبلغ">
                  <input dir="ltr" className={inputClass} value={amount} onChange={(event) => setAmount(event.target.value)} />
                </Field>
                <Field label="درصد تخفیف">
                  <input dir="ltr" className={inputClass} value={discount} onChange={(event) => setDiscount(event.target.value)} />
                </Field>
              </>
            ) : (
              <>
                <Field label="گیرنده">
                  <input dir="ltr" className={inputClass} value={to} onChange={(event) => setTo(event.target.value)} />
                </Field>
                {actionType === "email" ? (
                  <Field label="موضوع">
                    <input className={inputClass} value={subject} onChange={(event) => setSubject(event.target.value)} />
                  </Field>
                ) : null}
              </>
            )}
          </div>
          <div className="mt-3">
            <Field label="متن">
              <textarea className={`${inputClass} min-h-20`} value={body} onChange={(event) => setBody(event.target.value)} />
            </Field>
          </div>
          <div className="mt-3">
            <Button type="button" onClick={() => void createRequest()}>ثبت درخواست</Button>
          </div>
        </Card>
      ) : null}
      <div className="space-y-3">
        {rows.map((row) => (
          <Card key={row.id}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="font-bold">{actionLabel[row.action_type] || row.action_type}</h2>
                <p className="text-xs text-stone-500">{row.requested_by_name || "کاربر"}{row.agent_name ? ` · ${row.agent_name}` : ""}</p>
              </div>
              <div className="flex gap-2">
                <Badge tone={row.status === "pending" ? "amber" : row.status === "approved" ? "teal" : "rose"}>
                  {approvalStatus[row.status] || row.status}
                </Badge>
                <Badge>{executionStatus[row.execution_status] || row.execution_status}</Badge>
              </div>
            </div>
            <pre dir="ltr" className="mt-3 overflow-x-auto rounded-xl bg-stone-50 p-3 text-left text-xs">{JSON.stringify(row.payload, null, 2)}</pre>
            {canAct && row.status === "pending" ? (
              <div className="mt-3 flex gap-2">
                <Button type="button" onClick={() => void decide(row.id, "approved")}>تأیید</Button>
                <Button type="button" tone="danger" onClick={() => void decide(row.id, "rejected")}>رد</Button>
              </div>
            ) : null}
          </Card>
        ))}
        {rows.length === 0 ? <p className="text-sm text-stone-500">درخواستی ثبت نشده است.</p> : null}
      </div>
    </div>
  );
}
