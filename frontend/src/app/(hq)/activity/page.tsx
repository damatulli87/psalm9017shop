"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Event = {
  id: number;
  event_type: string;
  actor: string;
  summary: string;
  created_at: string;
};

function severity(eventType: string): "success" | "warn" | "error" {
  if (eventType.includes("fail") || eventType.includes("block") || eventType.includes("rejected")) return "error";
  if (eventType.includes("retry") || eventType.includes("requested") || eventType.includes("awaiting")) return "warn";
  return "success";
}

export default function ActivityPage() {
  const [events, setEvents] = useState<Event[]>([]);

  function refresh() {
    apiFetch<Event[]>("/activity?limit=150").then(setEvents).catch(() => {});
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold neon-text">Activity Monitor</h1>
        <p className="label-dim mt-1">Live audit log, polled every 5s. Only real agent/system events appear here.</p>
      </div>
      <div className="panel p-5 max-h-[70vh] overflow-y-auto">
        <ul className="space-y-3 text-sm">
          {events.map((e) => (
            <li key={e.id} className={`feed-line feed-${severity(e.event_type)}`}>
              <div className="flex justify-between gap-3">
                <span className="chip chip-neon">{e.event_type}</span>
                <span className="label-dim shrink-0">{new Date(e.created_at).toLocaleString()}</span>
              </div>
              <div className="text-xs text-[var(--text-dim)] mt-1">
                [{e.actor}] {e.summary}
              </div>
            </li>
          ))}
          {events.length === 0 && <p className="label-dim">No activity recorded yet.</p>}
        </ul>
      </div>
    </div>
  );
}
