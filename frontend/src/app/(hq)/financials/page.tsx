"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Report = {
  generated_at: string;
  ACTUAL: {
    gross_sales_usd: number;
    refunds_usd: number;
    net_revenue_usd: number;
    total_expenses_usd: number;
    operating_profit_usd: number;
    expenses_by_category: Record<string, number>;
  };
  PROJECTED: { projected_sales_usd: number; note: string };
  UNKNOWN: { note: string };
  month_to_date_total_spend_usd: number;
};

export default function FinancialsPage() {
  const [report, setReport] = useState<Report | null>(null);

  useEffect(() => {
    apiFetch<Report>("/financials/report").then(setReport).catch(() => {});
  }, []);

  if (!report) return <p className="label-dim">Loading financial ledger...</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold neon-text">Financial Command Center</h1>
        <p className="label-dim mt-1">ACTUAL / PROJECTED / UNKNOWN are never blended.</p>
      </div>

      <div className="grid md:grid-cols-4 gap-4">
        <div className="panel p-5">
          <div className="label-dim">Gross Sales (ACTUAL)</div>
          <div className="text-2xl font-semibold">${report.ACTUAL.gross_sales_usd.toFixed(2)}</div>
        </div>
        <div className="panel p-5">
          <div className="label-dim">Net Revenue (ACTUAL)</div>
          <div className="text-2xl font-semibold">${report.ACTUAL.net_revenue_usd.toFixed(2)}</div>
        </div>
        <div className="panel p-5">
          <div className="label-dim">Total Expenses (ACTUAL)</div>
          <div className="text-2xl font-semibold">${report.ACTUAL.total_expenses_usd.toFixed(2)}</div>
        </div>
        <div className="panel p-5" style={{ borderColor: "var(--accent-border)" }}>
          <div className="label-dim">Operating Profit (ACTUAL)</div>
          <div className="text-2xl font-semibold" style={{ color: "var(--accent-strong)" }}>${report.ACTUAL.operating_profit_usd.toFixed(2)}</div>
        </div>
      </div>

      <div className="panel p-5">
        <h2 className="font-bold mb-3">Expenses by Category (ACTUAL)</h2>
        {Object.keys(report.ACTUAL.expenses_by_category).length === 0 ? (
          <p className="label-dim">No real expenses recorded yet.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {Object.entries(report.ACTUAL.expenses_by_category).map(([cat, amt]) => (
              <li key={cat} className="flex justify-between border-b border-[var(--border)] pb-1">
                <span className="capitalize">{cat}</span>
                <span>${amt.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel p-5 border-[var(--warning)]">
        <h2 className="font-bold mb-2 text-[var(--warning)]">PROJECTED (not real revenue)</h2>
        <p className="text-sm">${report.PROJECTED.projected_sales_usd.toFixed(2)}</p>
        <p className="text-xs text-[var(--text-dim)] mt-1">{report.PROJECTED.note}</p>
      </div>

      <div className="panel p-5">
        <h2 className="font-bold mb-2">UNKNOWN</h2>
        <p className="text-xs text-[var(--text-dim)]">{report.UNKNOWN.note}</p>
      </div>
    </div>
  );
}
