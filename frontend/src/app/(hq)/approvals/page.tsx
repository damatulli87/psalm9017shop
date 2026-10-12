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
  requested_at: string;
};

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
              <div>
                <span className="text-xs px-2 py-0.5 rounded bg-black/40 border border-[var(--border)] mr-2">
                  {a.action_type}
                </span>
                <span
                  className={`text-xs px-2 py-0.5 rounded border ${
                    a.risk_level === "high"
                      ? "border-[var(--danger)] text-[var(--danger)]"
                      : "border-[var(--warning)] text-[var(--warning)]"
                  }`}
                >
                  {a.risk_level} risk
                </span>
              </div>
              <span className="label-dim">#{a.id} -- requested by {a.requested_by_agent}</span>
            </div>
            <p className="mt-3 text-sm">{a.summary}</p>
            <p className="text-xs text-[var(--text-dim)] mt-1">
              Estimated cost: ${a.estimated_cost_usd.toFixed(2)}
            </p>
            <pre className="text-[10px] bg-black/30 p-2 rounded mt-2 overflow-x-auto">
              {JSON.stringify(a.payload, null, 2)}
            </pre>
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
