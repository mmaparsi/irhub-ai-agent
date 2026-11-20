"use client";

import { errorText, useAuth } from "@/components/AuthProvider";
import { Button, ErrorNote, inputClass } from "@/components/ui";
import { api, streamMessage } from "@/lib/api";
import { channelLabel } from "@/lib/labels";
import type { Agent, ChatMessage, Conversation } from "@/lib/types";
import { useEffect, useRef, useState } from "react";

export default function ChatPage() {
  const { user } = useAuth();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [agentId, setAgentId] = useState("auto");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [tier, setTier] = useState<"strong" | "fast">("strong");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const canSend = user?.role === "admin" || user?.role === "sales" || user?.role === "supplier_acquisition";

  useEffect(() => {
    api<Agent[]>("/api/agents").then((rows) => setAgents(rows.filter((item) => item.is_active))).catch((err) => setError(errorText(err)));
    api<Conversation[]>("/api/conversations").then(setConversations).catch(() => undefined);
  }, []);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [messages, streaming]);

  async function openConversation(id: string) {
    setError("");
    setNotice("");
    const detail = await api<Conversation & { messages: ChatMessage[] }>(`/api/conversations/${id}`);
    setConversationId(detail.id);
    setAgentId(detail.agent_id || "auto");
    setMessages(detail.messages);
  }

  async function send() {
    const content = draft.trim();
    if (!content || !canSend || streaming) return;
    setError("");
    setNotice("");
    setStreaming(true);
    setDraft("");
    const localUser: ChatMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content,
      seq: messages.length + 1,
      created_at: new Date().toISOString(),
    };
    const localAssistant: ChatMessage = {
      id: `local-a-${Date.now()}`,
      role: "assistant",
      content: "",
      seq: messages.length + 2,
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, localUser, localAssistant]);
    try {
      let id = conversationId;
      if (!id) {
        const created = await api<Conversation>("/api/conversations", {
          method: "POST",
          body: JSON.stringify({
            agent_id: agentId === "auto" ? null : agentId,
            title: content.slice(0, 80),
          }),
        });
        id = created.id;
        setConversationId(id);
      }
      const result = await streamMessage(id, content, tier, (token) => {
        setMessages((current) => {
          const next = [...current];
          const last = next[next.length - 1];
          if (last && last.role === "assistant") next[next.length - 1] = { ...last, content: last.content + token };
          return next;
        });
      });
      if (result.approvalIds.length) {
        setNotice("اقدام خروجی ارسال نشد و در صف تأیید کارشناس قرار گرفت.");
      }
      const refreshed = await api<Conversation[]>("/api/conversations");
      setConversations(refreshed);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-4 lg:grid-cols-[16rem_1fr]">
      <aside className="space-y-3">
        <label className="block text-sm">
          <span className="mb-1 block font-medium">عامل</span>
          <select
            className={inputClass}
            value={agentId}
            onChange={(event) => {
              setAgentId(event.target.value);
              setConversationId(null);
              setMessages([]);
              setNotice("");
            }}
          >
            <option value="auto">انتخاب خودکار (سرپرست)</option>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name_fa}
              </option>
            ))}
          </select>
        </label>
        <div className="space-y-1">
          {conversations.map((item) => (
            <button
              key={item.id}
              className={`block w-full rounded-xl px-3 py-2 text-right text-sm ${item.id === conversationId ? "bg-teal-800 text-white" : "bg-white text-stone-700"}`}
              onClick={() => openConversation(item.id).catch((err) => setError(errorText(err)))}
            >
              <span className="block truncate">{item.title}</span>
              <span className="block truncate text-xs opacity-70">
                {channelLabel[item.channel || "panel"] || item.channel} · {item.agent_name || "سرپرست"}
              </span>
            </button>
          ))}
        </div>
      </aside>
      <section className="flex min-h-[70vh] flex-col rounded-2xl border border-[#e6dfd2] bg-[#fffcf7]">
        <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <p className="text-sm text-stone-500">یک عامل را انتخاب کنید یا بگذارید سرپرست بر اساس متن، کار را مسیر دهد.</p>
          ) : null}
          {messages.map((message) => (
            <div
              key={message.id}
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-7 ${
                message.role === "user" ? "bg-teal-800 text-white" : "ms-auto border border-[#e6dfd2] bg-white text-stone-800"
              }`}
            >
              {message.content || (streaming ? "…" : "")}
            </div>
          ))}
        </div>
        <div className="space-y-2 border-t border-[#e6dfd2] p-3">
          {error ? <ErrorNote>{error}</ErrorNote> : null}
          {notice ? <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-950">{notice}</p> : null}
          <div className="flex gap-2">
            <select className={`${inputClass} max-w-28`} value={tier} onChange={(event) => setTier(event.target.value as "strong" | "fast")}>
              <option value="strong">قوی</option>
              <option value="fast">سریع</option>
            </select>
            <textarea
              className={`${inputClass} min-h-12 flex-1`}
              placeholder={canSend ? "پیام خود را بنویسید" : "نقش بیننده فقط می‌تواند گفتگوها را ببیند"}
              value={draft}
              disabled={!canSend || streaming}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
            <Button type="button" disabled={!canSend || streaming || !draft.trim()} onClick={() => void send()}>
              {streaming ? "…" : "ارسال"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
