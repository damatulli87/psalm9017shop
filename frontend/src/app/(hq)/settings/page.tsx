"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Policy = { key: string; value: unknown; version: number };
type Budget = {
  startup_budget_ceiling_usd: number;
  monthly_ai_budget_usd: number;
  advertising_enabled: boolean;
  max_spend_per_action_usd: number;
  max_spend_per_workflow_usd: number;
  daily_product_generation_limit: number;
};
type Integration = { provider: string; status: string };

export default function SettingsPage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [integrations, setIntegrations] = useState<Integration[]>([]);

  useEffect(() => {
    apiFetch<Policy[]>("/settings/policies").then(setPolicies).catch(() => {});
    apiFetch<Budget>("/settings/budget").then(setBudget).catch(() => {});
    apiFetch<Integration[]>("/settings/integrations").then(setIntegrations).catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold neon-text">Settings</h1>
        <p className="label-dim mt-1">
          Budgets and spend caps are hard-enforced server-side (app/config.py + policy engine) -- the UI is
          read-only for safety-critical limits in this build.
        </p>
      </div>

      {budget && (
        <div className="panel p-5">
          <h2 className="font-bold mb-3">Budget</h2>
          <ul className="text-sm space-y-1">
            <li>Startup budget ceiling: ${budget.startup_budget_ceiling_usd.toFixed(2)}</li>
            <li>Monthly AI budget: ${budget.monthly_ai_budget_usd.toFixed(2)}</li>
            <li>Max spend per action: ${budget.max_spend_per_action_usd.toFixed(2)}</li>
            <li>Max spend per workflow: ${budget.max_spend_per_workflow_usd.toFixed(2)}</li>
            <li>Daily product generation limit: {budget.daily_product_generation_limit}</li>
            <li>
              Advertising enabled:{" "}
              <span className={budget.advertising_enabled ? "text-[var(--neon)]" : "text-[var(--warning)]"}>
                {budget.advertising_enabled ? "yes" : "no (disabled by default policy)"}
              </span>
            </li>
          </ul>
        </div>
      )}

      <div className="panel p-5">
        <h2 className="font-bold mb-3">Operating Policies</h2>
        <ul className="text-sm space-y-2">
          {policies.map((p) => (
            <li key={p.key} className="border-b border-[var(--border)] pb-2">
              <div className="font-bold">{p.key} <span className="label-dim">v{p.version}</span></div>
              <pre className="text-[10px] bg-black/30 p-2 rounded mt-1 overflow-x-auto">
                {JSON.stringify(p.value, null, 2)}
              </pre>
            </li>
          ))}
        </ul>
      </div>

      <div className="panel p-5">
        <h2 className="font-bold mb-3">Integration Credentials</h2>
        <ul className="text-sm space-y-1">
          {integrations.map((i) => (
            <li key={i.provider} className="flex justify-between border-b border-[var(--border)] pb-1">
              <span className="capitalize">{i.provider}</span>
              <span className={i.status === "configured" ? "text-[var(--neon)]" : "text-[var(--warning)]"}>
                {i.status}
              </span>
            </li>
          ))}
        </ul>
        <p className="text-xs text-[var(--text-dim)] mt-3">
          Add real credentials in backend/.env (copy from .env.example) and restart the backend to activate.
        </p>
      </div>
    </div>
  );
}
