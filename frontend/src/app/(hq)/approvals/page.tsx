"use client";

import { useEffect, useState } from "react";
import { apiFetch, API_BASE, getToken } from "@/lib/api";

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

type ProductPreview = {
  id: number;
  title: string;
  product_type: string;
  format: string;
  status: string;
  recommended_price_usd: number;
  assets: { id: number; asset_type: string; file_size_bytes: number }[];
  qa_results: { check_name: string; passed: boolean; details: string }[];
  listing: {
    id: number;
    status: string;
    title: string;
    description: string;
    price_usd: number;
    tags: string[];
    is_simulated: boolean;
  } | null;
};

type Finding = { check: string; status: "pass" | "warn" | "fail"; detail: string };

function titleCase(slug: string): string {
  return slug.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function ProductPreviewCard({ productId }: { productId: number }) {
  const [product, setProduct] = useState<ProductPreview | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    apiFetch<ProductPreview>(`/products/${productId}`).then(setProduct).catch(() => setError(true));
  }, [productId]);

  function downloadUrl(assetId: number) {
    return `${API_BASE}/products/${productId}/assets/${assetId}/download`;
  }

  if (error) return <p className="text-xs text-[var(--danger)] mt-3">Could not load product #{productId}.</p>;
  if (!product) return <p className="text-xs text-[var(--text-faint)] mt-3">Loading product preview...</p>;

  const failedChecks = product.qa_results.filter((r) => !r.passed);

  return (
    <div className="panel-raised p-4 mt-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">{product.title}</div>
          <div className="text-[11px] text-[var(--text-faint)] mt-0.5 uppercase tracking-wide">
            {product.product_type} -- {product.format}
          </div>
        </div>
        <div className="text-sm font-semibold shrink-0">${product.recommended_price_usd.toFixed(2)}</div>
      </div>

      {product.listing && (
        <div className="mt-3">
          <div className="label-dim mb-1">Listing title</div>
          <div className="text-xs">{product.listing.title}</div>
          <div className="label-dim mt-2 mb-1">Listing description (what buyers will see)</div>
          <div className="text-xs text-[var(--text-dim)] whitespace-pre-wrap bg-black/20 rounded p-2 max-h-40 overflow-y-auto">
            {product.listing.description}
          </div>
          {product.listing.tags?.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {product.listing.tags.map((t) => (
                <span key={t} className="chip chip-dim !text-[9px]">{t}</span>
              ))}
            </div>
          )}
          {product.listing.is_simulated && (
            <p className="text-[10px] text-[var(--amber-strong)] mt-2">
              Etsy not connected -- this will be recorded as a simulated draft, not sent to Etsy for real.
            </p>
          )}
        </div>
      )}

      <div className="mt-3">
        <div className="label-dim mb-1">Quality checks</div>
        <div className="text-xs">
          {failedChecks.length === 0 ? (
            <span className="text-[var(--success-strong)]">All {product.qa_results.length} checks passed</span>
          ) : (
            <span className="text-[var(--danger)]">{failedChecks.length} of {product.qa_results.length} checks failed</span>
          )}
        </div>
      </div>

      {product.assets.length > 0 && (
        <div className="mt-3">
          <div className="label-dim mb-1">Files (download to inspect yourself)</div>
          <div className="flex flex-wrap gap-2">
            {product.assets.map((a) => (
              <a
                key={a.id}
                className="chip chip-blue !text-[10px] cursor-pointer"
                onClick={(e) => {
                  e.preventDefault();
                  fetch(downloadUrl(a.id), { headers: { Authorization: `Bearer ${getToken()}` } })
                    .then((r) => r.blob())
                    .then((blob) => {
                      const url = URL.createObjectURL(blob);
                      const link = document.createElement("a");
                      link.href = url;
                      link.download = `product_${productId}_${a.asset_type}`;
                      link.click();
                    });
                }}
              >
                {a.asset_type} ({Math.round(a.file_size_bytes / 1024)} KB)
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FindingsPreview({ findings }: { findings: Finding[] }) {
  return (
    <div className="panel-raised p-4 mt-3">
      <div className="label-dim mb-2">What Psalm 90:17 found</div>
      <ul className="space-y-1.5">
        {findings.map((f, i) => (
          <li key={i} className="text-xs">
            <span
              className="font-semibold"
              style={{ color: f.status === "pass" ? "var(--success-strong)" : f.status === "warn" ? "var(--amber-strong)" : "var(--danger)" }}
            >
              {f.status.toUpperCase()}
            </span>{" "}
            <span className="text-[var(--text-dim)]">{f.check} -- {f.detail}</span>
          </li>
        ))}
      </ul>
    </div>
  );
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
        {approvals.map((a) => {
          const productId = typeof a.payload.product_id === "number" ? a.payload.product_id : null;
          const findings = Array.isArray(a.payload.findings) ? (a.payload.findings as Finding[]) : null;

          return (
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

              {productId && <ProductPreviewCard productId={productId} />}
              {findings && <FindingsPreview findings={findings} />}

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
          );
        })}
      </div>
    </div>
  );
}
