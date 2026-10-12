"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import FactoryMap from "@/components/FactoryMap";

type Mission = {
  id: number;
  title: string;
  status: string;
  created_by: string;
  created_at: string;
  completed_at: string | null;
};

type RunResult = {
  mission_id: number;
  workflow_run_id: number;
  status: string;
  current_stage: string;
  error: string | null;
};

export default function MissionsPage() {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [running, setRunning] = useState(false);
  const [lastResult, setLastResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    apiFetch<Mission[]>("/missions").then(setMissions).catch((e) => setError(String(e)));
  }

  useEffect(() => {
    refresh();
  }, []);

  async function runPipeline() {
    setRunning(true);
    setError(null);
    try {
      const result = await apiFetch<RunResult>("/missions/run-digital-pipeline", {
        method: "POST",
        body: JSON.stringify({ title: "Owner-triggered discovery run", niche_limit: 5 }),
      });
      setLastResult(result);
      refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold neon-text">Mission Control</h1>
        <p className="label-dim mt-1">
          Trigger the real research -&gt; select -&gt; produce -&gt; QA -&gt; list -&gt; approve pipeline.
        </p>
      </div>

      <div className="panel p-5">
        <h2 className="font-bold mb-2">Run digital product discovery pipeline</h2>
        <p className="text-xs text-[var(--text-dim)] mb-4">
          Researches candidate niches (real Google Trends signal where reachable), scores and selects the
          best opportunity, generates an actual digital product, QA-validates it, prepares an Etsy listing
          draft, and queues it in the Approval Center.
        </p>
        <button className="btn-neon" disabled={running} onClick={runPipeline}>
          {running ? "Running pipeline..." : "▶ Run Pipeline Now"}
        </button>

        {error && <p className="text-[var(--danger)] mt-3 text-sm">{error}</p>}
        {lastResult && (
          <div className="mt-4 text-sm panel-raised p-3">
            <div>Workflow run #{lastResult.workflow_run_id}</div>
            <div className="label-dim">Status: {lastResult.status} ({lastResult.current_stage})</div>
            {lastResult.error && <div className="text-[var(--danger)]">{lastResult.error}</div>}
          </div>
        )}
      </div>

      <FactoryMap />

      <div className="panel p-5">
        <h2 className="font-bold mb-3">Mission History</h2>
        {missions.length === 0 && <p className="label-dim">No missions run yet.</p>}
        <table className="w-full text-sm">
          <thead>
            <tr className="label-dim text-left border-b border-[var(--border)]">
              <th className="py-2">#</th>
              <th>Title</th>
              <th>Status</th>
              <th>Created By</th>
            </tr>
          </thead>
          <tbody>
            {missions.map((m) => (
              <tr key={m.id} className="border-b border-[var(--border)]">
                <td className="py-2">{m.id}</td>
                <td>{m.title}</td>
                <td className="text-[var(--neon)]">{m.status}</td>
                <td className="text-[var(--text-dim)]">{m.created_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
