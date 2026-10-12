"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Approval = {
  id: number;
  action_type: string;
  summary: string;
  payload: Record<string, unknown>;
  estimated_cost_usd: number;
  risk_level: string;
  status: string;
  requested_by_agent: string;
  requested_by_agent_name: string;
  requested_at: string;
};

function titleCase(slug: string): string {
  return slug.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);

  function refresh() {
    apiFetch<Approval[]>("/approvals?status_filter=pending").then(setApprovals).catch(() => {});
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, []);

  async function decide(id: number, approve: boolean) {
    setBusyId(id);
    try {
      await apiFetch(`/approvals/${id}/decide`, {
        method: "POST",
        body: JSON.stringify({ approve, notes: approve ? "Approved via command center" : "Rejected via command center" }),
      });
      refresh();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold neon-text">Approval Center</h1>
        <p className="label-dim mt-1">
          Every action here requires a real decision -- agents cannot self-authorize.
        </p>
      </div>

      {approvals.length === 0 && <p className="label-dim">Nothing pending your approval right now.</p>}

      <div className="space-y-4">
        {approvals.map((a) => (
          <div key={a.id} className="panel p-5">
            <div className="flex justify-between items-start">
              <div className="flex gap-2">
                <span className="chip chip-dim">{titleCase(a.action_type)}</span>
                <span className={`chip ${a.risk_level === "high" ? "chip-danger" : "chip-amber"}`}>
                  {titleCase(a.risk_level)} risk
                </span>
              </div>
              <span className="label-dim">#{a.id} -- requested by {a.requested_by_agent_name}</span>
            </div>
            <p className="mt-3 text-sm">{a.summary}</p>
            <p className="text-xs text-[var(--text-dim)] mt-1">
              Estimated cost: ${a.estimated_cost_usd.toFixed(2)}
            </p>
            {Object.keys(a.payload).length > 0 && (
              <details className="mt-2">
                <summary className="text-xs cursor-pointer text-[var(--text-faint)] hover:text-[var(--text-dim)]">
                  Technical details
                </summary>
                <pre className="text-[10px] bg-black/30 p-2 rounded mt-2 overflow-x-auto">
                  {JSON.stringify(a.payload, null, 2)}
                </pre>
              </details>
            )}
            <div className="flex gap-3 mt-4">
              <button className="btn-neon" disabled={busyId === a.id} onClick={() => decide(a.id, true)}>
                Approve
              </button>
              <button className="btn-danger" disabled={busyId === a.id} onClick={() => decide(a.id, false)}>
                Reject
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
