"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Event = { id: number; event_type: string; actor: string; actor_name: string; summary: string; created_at: string };

function severity(eventType: string): "success" | "warn" | "error" {
  if (eventType.includes("fail") || eventType.includes("block") || eventType.includes("rejected")) return "error";
  if (eventType.includes("retry") || eventType.includes("requested") || eventType.includes("awaiting")) return "warn";
  return "success";
}

function titleCase(slug: string): string {
  return slug.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function OperationsFeed({ limit = 12, title = "Operations Feed" }: { limit?: number; title?: string }) {
  const [events, setEvents] = useState<Event[]>([]);

  useEffect(() => {
    let cancelled = false;
    function load() {
      apiFetch<Event[]>(`/activity?limit=${limit}`)
        .then((e) => !cancelled && setEvents(e))
        .catch(() => {});
    }
    load();
    const interval = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [limit]);

  return (
    <div className="panel p-5">
      <h2 className="font-bold mb-3">{title}</h2>
      {events.length === 0 && <p className="label-dim">No activity yet -- run a mission to populate this feed.</p>}
      <ul className="space-y-3 max-h-80 overflow-y-auto pr-1">
        {events.map((e) => (
          <li key={e.id} className={`feed-line feed-${severity(e.event_type)} text-xs`}>
            <div className="flex justify-between gap-2">
              <span className="font-bold">{titleCase(e.event_type)}</span>
              <span className="text-[var(--text-dim)] shrink-0">
                {new Date(e.created_at).toLocaleTimeString()}
              </span>
            </div>
            <div className="text-[var(--text-dim)]">
              <span className="text-[var(--text)]">{e.actor_name}</span> -- {e.summary}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
