"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

type ChatTurn = { role: "owner" | "ultron"; text: string };

export default function ChatPage() {
  const [turns, setTurns] = useState<ChatTurn[]>([
    {
      role: "ultron",
      text: "Psalm 90:17 online. I can run the research pipeline, show pending approvals, or report on paid activity. Full open-ended command parsing is still limited -- see PROGRESS.md.",
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  async function send() {
    if (!input.trim()) return;
    const message = input;
    setInput("");
    setTurns((t) => [...t, { role: "owner", text: message }]);
    setSending(true);
    try {
      const res = await apiFetch<{ reply: string }>("/chat", {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      setTurns((t) => [...t, { role: "ultron", text: res.reply }]);
    } catch (e) {
      setTurns((t) => [...t, { role: "ultron", text: `Error: ${String(e)}` }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-6 flex flex-col h-[calc(100vh-3rem)]">
      <div>
        <h1 className="text-2xl font-bold neon-text">Executive AI Chat</h1>
        <p className="label-dim mt-1">Natural-language commands that trigger real backend workflows.</p>
      </div>
      <div className="panel p-5 flex-1 overflow-y-auto space-y-3">
        {turns.map((t, i) => (
          <div key={i} className={t.role === "owner" ? "text-right" : "text-left"}>
            <span
              className={`inline-block px-3 py-2 rounded max-w-[80%] text-sm ${
                t.role === "owner" ? "bg-[var(--neon-glow)] text-[var(--neon)]" : "panel-raised"
              }`}
            >
              {t.text}
            </span>
          </div>
        ))}
      </div>
      <div className="flex gap-3">
        <input
          className="flex-1 bg-black/40 border border-[var(--border)] rounded px-3 py-2 text-sm focus:outline-none focus:border-[var(--neon-dim)]"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder='Try: "run research" or "show pending approvals"'
        />
        <button className="btn-neon" disabled={sending} onClick={send}>
          Send
        </button>
      </div>
    </div>
  );
}
