"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import FactoryMap from "@/components/FactoryMap";
import OperationsFeed from "@/components/OperationsFeed";

type SystemReview = { verdict: "pass" | "warning" | "blocked"; summary: string; created_at: string } | null;

const VERDICT_STYLE: Record<string, string> = { pass: "chip-neon", warning: "chip-amber", blocked: "chip-danger" };

type Summary = {
  today_sales_actual_usd: number;
  month_sales_actual_usd: number;
  month_operating_profit_actual_usd: number;
  month_expenses_actual_usd: number;
  startup_budget_ceiling_usd: number;
  month_to_date_spend_usd: number;
  autonomy_mode: string;
  active_agent_count: number;
  total_agent_count: number;
  products_in_development: number;
  published_listings: number;
  pending_approvals: number;
  recent_workflow_runs: { id: number; type: string; status: string; stage: string | null }[];
  storefront_connections: { channel: string; connected: boolean; status: string }[];
  system_health: string;
};

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="panel p-5">
      <div className="label-dim">{label}</div>
      <div className="text-3xl font-bold mt-2 neon-text">{value}</div>
      {sub && <div className="text-xs text-[var(--text-dim)] mt-1">{sub}</div>}
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ultron, setUltron] = useState<SystemReview>(null);

  useEffect(() => {
    apiFetch<Summary>("/dashboard/summary").then(setData).catch((e) => setError(String(e)));
    apiFetch<SystemReview>("/oversight/reviews/latest-system").then(setUltron).catch(() => {});
  }, []);

  if (error) return <p className="text-[var(--danger)]">{error}</p>;
  if (!data) return <p className="label-dim">Loading live operating state...</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold neon-text">Executive Dashboard</h1>
        <p className="label-dim mt-1">
          All figures below are read live from the database -- ACTUAL, never simulated.
        </p>
      </div>

      <Link href="/oversight" className="panel p-5 flex items-center justify-between block hover:border-[var(--accent-border)] transition-colors">
        <div>
          <div className="label-dim">ULTRON Oversight Verdict</div>
          <div className="text-sm text-[var(--text-dim)] mt-1">{ultron ? ultron.summary : "No health check has run yet."}</div>
        </div>
        {ultron && <span className={`chip ${VERDICT_STYLE[ultron.verdict]} shrink-0`}>{ultron.verdict.toUpperCase()}</span>}
      </Link>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Tile label="Today's Sales (Actual)" value={`$${data.today_sales_actual_usd.toFixed(2)}`} />
        <Tile label="Month Sales (Actual)" value={`$${data.month_sales_actual_usd.toFixed(2)}`} />
        <Tile
          label="Operating Profit (Actual)"
          value={`$${data.month_operating_profit_actual_usd.toFixed(2)}`}
        />
        <Tile
          label="Spend vs Startup Cap"
          value={`$${data.month_to_date_spend_usd.toFixed(2)} / $${data.startup_budget_ceiling_usd.toFixed(0)}`}
        />
        <Tile label="Autonomy Mode" value={data.autonomy_mode} />
        <Tile label="Active Agents" value={`${data.active_agent_count} / ${data.total_agent_count}`} />
        <Tile label="Products In Development" value={String(data.products_in_development)} />
        <Tile label="Pending Approvals" value={String(data.pending_approvals)} />
      </div>

      <FactoryMap />

      <div className="grid md:grid-cols-2 gap-4">
        <OperationsFeed limit={10} />
        <div className="panel p-5">
          <h2 className="font-bold mb-3">Marketplace Connections</h2>
          <ul className="space-y-2">
            {data.storefront_connections.map((s) => (
              <li key={s.channel} className="flex justify-between text-sm border-b border-[var(--border)] pb-2">
                <span className="capitalize">{s.channel}</span>
                <span className={s.connected ? "text-[var(--neon)]" : "text-[var(--text-dim)]"}>
                  {s.connected ? "Connected" : "Awaiting configuration"}
                </span>
              </li>
            ))}
          </ul>
          <h2 className="font-bold mb-3 mt-5">Recent Workflow Runs</h2>
          {data.recent_workflow_runs.length === 0 && <p className="label-dim">No workflow runs yet.</p>}
          <ul className="space-y-2">
            {data.recent_workflow_runs.map((r) => (
              <li key={r.id} className="flex justify-between text-sm border-b border-[var(--border)] pb-2">
                <span>#{r.id} {r.type}</span>
                <span className="text-[var(--text-dim)]">{r.status} {r.stage ? `(${r.stage})` : ""}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
