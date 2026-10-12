"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import FactoryMap from "@/components/FactoryMap";

type Agent = {
  key: string;
  name: string;
  responsibility: string;
  status: string;
  current_task: string | null;
  tools: string[];
  total_cost_usd: number;
  ai_call_count: number;
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function refresh() {
      apiFetch<Agent[]>("/agents").then(setAgents).catch((e) => setError(String(e)));
    }
    refresh();
    const interval = setInterval(refresh, 6000);
    return () => clearInterval(interval);
  }, []);

  if (error) return <p className="text-[var(--danger)]">{error}</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold neon-text">AI Agent Network</h1>
        <p className="label-dim mt-1">
          {agents.length} agents registered. Status reflects real execution state, not a simulation.
        </p>
      </div>

      <FactoryMap />

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map((a) => (
          <div key={a.key} className="panel p-5">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-bold">{a.name}</h3>
              <span className={`status-dot ${a.status}`} title={a.status} />
            </div>
            <p className="text-xs text-[var(--text-dim)] mb-3">{a.responsibility}</p>
            {a.current_task && (
              <p className="text-xs mb-2">
                <span className="label-dim">Current task:</span> {a.current_task}
              </p>
            )}
            <div className="flex flex-wrap gap-1.5 mb-3">
              {a.tools.map((t) => (
                <span key={t} className="chip chip-dim">
                  {t}
                </span>
              ))}
            </div>
            <div className="flex justify-between text-xs text-[var(--text-dim)] border-t border-[var(--border)] pt-2">
              <span>AI calls: {a.ai_call_count}</span>
              <span>Cost: ${a.total_cost_usd.toFixed(4)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
