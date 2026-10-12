"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiFetch, API_BASE } from "@/lib/api";

type IntegrationStatus = { provider: string; status: string; last_verified_at: string | null };
type Product = { id: number; title: string; status: string };

const STATUS_LABEL: Record<string, string> = {
  connected: "Connected",
  configured: "Configured (OAuth not completed)",
  awaiting_configuration: "Awaiting configuration",
};
const STATUS_CHIP: Record<string, string> = {
  connected: "chip-neon",
  configured: "chip-amber",
  awaiting_configuration: "chip-dim",
};

export default function MarketplacePage() {
  const [integrations, setIntegrations] = useState<IntegrationStatus[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [disconnecting, setDisconnecting] = useState(false);
  const searchParams = useSearchParams();
  const etsyCallback = searchParams.get("etsy");

  function refresh() {
    apiFetch<IntegrationStatus[]>("/settings/integrations").then(setIntegrations).catch(() => {});
    apiFetch<Product[]>("/products").then(setProducts).catch(() => {});
  }

  useEffect(() => {
    refresh();
  }, []);

  async function disconnectEtsy() {
    setDisconnecting(true);
    try {
      await apiFetch("/integrations/etsy/disconnect", { method: "POST" });
      refresh();
    } finally {
      setDisconnecting(false);
    }
  }

  const etsy = integrations.find((i) => i.provider === "etsy");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold neon-text">Marketplace Center</h1>
        <p className="label-dim mt-1">
          Connection status is verified against real configuration -- never claimed without it.
        </p>
      </div>

      {etsyCallback === "connected" && (
        <div className="panel p-4 border-l-4" style={{ borderLeftColor: "var(--accent)" }}>
          <span className="text-sm font-semibold text-[var(--accent-strong)]">Etsy connected successfully.</span>
          <span className="text-xs text-[var(--text-dim)]"> New listing drafts will now be sent to Etsy for real.</span>
        </div>
      )}
      {etsyCallback === "error" && (
        <div className="panel p-4 border-l-4" style={{ borderLeftColor: "var(--danger)" }}>
          <span className="text-sm font-semibold text-[var(--danger)]">Etsy connection failed.</span>
          <span className="text-xs text-[var(--text-dim)]"> {searchParams.get("detail") || "Unknown error."} Check backend/server.log for detail.</span>
        </div>
      )}

      <div className="panel p-5">
        <h2 className="font-bold mb-3">Integrations</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="label-dim text-left border-b border-[var(--border)]">
              <th className="py-2">Provider</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {integrations.map((i) => (
              <tr key={i.provider} className="border-b border-[var(--border)]">
                <td className="py-3 capitalize">{i.provider}</td>
                <td>
                  <span className={`chip ${STATUS_CHIP[i.status] || "chip-dim"}`}>
                    {STATUS_LABEL[i.status] || i.status}
                  </span>
                </td>
                <td className="text-right">
                  {i.provider === "etsy" && i.status === "configured" && (
                    <a href={`${API_BASE}/integrations/etsy/connect`} className="btn-neon !text-xs !py-1.5">
                      Connect Etsy
                    </a>
                  )}
                  {i.provider === "etsy" && i.status === "connected" && (
                    <button className="btn-danger !text-xs !py-1.5" disabled={disconnecting} onClick={disconnectEtsy}>
                      Disconnect
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {etsy?.status === "awaiting_configuration" && (
          <p className="text-xs text-[var(--text-dim)] mt-3">
            To connect Etsy: register an app at etsy.com/developers/your-apps, then set ETSY_API_KEY,
            ETSY_API_SECRET, and ETSY_SHOP_ID in backend/.env and restart the backend. A &quot;Connect
            Etsy&quot; button will appear here once those are set.
          </p>
        )}
        <p className="text-xs text-[var(--text-dim)] mt-2">
          Printify, Printful, and Shopify adapters are not built yet (see PROGRESS.md) -- POD production is a
          future phase.
        </p>
      </div>

      <div className="panel p-5">
        <h2 className="font-bold mb-3">Listing-Ready Products</h2>
        <ul className="space-y-2 text-sm">
          {products.map((p) => (
            <li key={p.id} className="flex justify-between border-b border-[var(--border)] pb-2">
              <span>#{p.id} {p.title}</span>
              <span className="label-dim">{p.status}</span>
            </li>
          ))}
          {products.length === 0 && <p className="label-dim">No products yet.</p>}
        </ul>
      </div>
    </div>
  );
}
