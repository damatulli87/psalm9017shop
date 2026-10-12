"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Finding = { check: string; status: "pass" | "warn" | "fail"; detail: string };
type Review = {
  id: number;
  scope: string;
  scope_id: string;
  verdict: "pass" | "warning" | "blocked";
  summary: string;
  findings: Finding[];
  created_at: string;
};

const VERDICT_STYLE: Record<string, string> = {
  pass: "chip-neon",
  warning: "chip-amber",
  blocked: "chip-danger",
};

function FindingRow({ f }: { f: Finding }) {
  const color = f.status === "pass" ? "var(--accent-strong)" : f.status === "warn" ? "var(--amber)" : "var(--danger)";
  const label = f.status === "pass" ? "PASS" : f.status === "warn" ? "WARN" : "FAIL";
  return (
    <div className="flex gap-3 py-2 border-b border-[var(--border-soft)] last:border-0">
      <span className="text-[10px] font-bold w-10 shrink-0" style={{ color }}>
        {label}
      </span>
      <div className="text-xs">
        <span className="font-semibold">{f.check}</span>
        <span className="text-[var(--text-dim)]"> -- {f.detail}</span>
      </div>
    </div>
  );
}

export default function OversightPage() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    apiFetch<Review[]>("/oversight/reviews?limit=30").then(setReviews).catch((e) => setError(String(e)));
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 8000);
    return () => clearInterval(interval);
  }, []);

  async function runCheckNow() {
    setRunning(true);
    try {
      await apiFetch("/oversight/system-check", { method: "POST" });
      refresh();
    } finally {
      setRunning(false);
    }
  }

  const latestSystem = reviews.find((r) => r.scope === "system");
  const runReviews = reviews.filter((r) => r.scope === "workflow_run");

  if (error) return <p className="text-[var(--danger)]">{error}</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold neon-text">ULTRON Oversight</h1>
          <p className="label-dim mt-1 max-w-2xl">
            ULTRON independently re-derives conclusions from raw data and compares them against what each agent
            reported -- it does not trust self-reported status. A blocked verdict opens a real entry in the
            Approval Center; it cannot resolve its own concerns.
          </p>
        </div>
        <button className="btn-neon shrink-0" disabled={running} onClick={runCheckNow}>
          {running ? "Running..." : "Run Health Check Now"}
        </button>
      </div>

      <div className="panel p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-[15px]">System Health</h2>
          {latestSystem && (
            <span className={`chip ${VERDICT_STYLE[latestSystem.verdict]}`}>{latestSystem.verdict.toUpperCase()}</span>
          )}
        </div>
        {!latestSystem && <p className="label-dim">No system health check has run yet.</p>}
        {latestSystem && (
          <>
            <p className="text-xs text-[var(--text-dim)] mb-3">{latestSystem.summary}</p>
            <div>
              {latestSystem.findings.map((f, i) => (
                <FindingRow key={i} f={f} />
              ))}
            </div>
            <p className="text-[10px] text-[var(--text-faint)] mt-3">
              Last checked {new Date(latestSystem.created_at).toLocaleString()} -- also runs automatically every day at 7:30am.
            </p>
          </>
        )}
      </div>

      <div className="panel p-6">
        <h2 className="font-semibold text-[15px] mb-4">Per-Run Reviews</h2>
        {runReviews.length === 0 && <p className="label-dim">No workflow runs have been reviewed yet.</p>}
        <div className="space-y-4">
          {runReviews.map((r) => (
            <div key={r.id} className="panel-raised p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold">Workflow Run #{r.scope_id}</span>
                <span className={`chip ${VERDICT_STYLE[r.verdict]}`}>{r.verdict.toUpperCase()}</span>
              </div>
              <p className="text-xs text-[var(--text-dim)] mb-2">{r.summary}</p>
              <details>
                <summary className="text-xs cursor-pointer text-[var(--text-dim)] hover:text-[var(--text)]">
                  {r.findings.length} checks -- view detail
                </summary>
                <div className="mt-2">
                  {r.findings.map((f, i) => (
                    <FindingRow key={i} f={f} />
                  ))}
                </div>
              </details>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
