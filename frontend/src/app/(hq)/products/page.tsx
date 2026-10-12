"use client";

import { useEffect, useState } from "react";
import { apiFetch, API_BASE, getToken } from "@/lib/api";

type Product = {
  id: number;
  title: string;
  product_type: string;
  format: string;
  status: string;
  recommended_price_usd: number;
  estimated_margin_usd: number;
};

type ProductDetail = {
  id: number;
  assets: { id: number; asset_type: string; file_size_bytes: number }[];
  qa_results: { check_name: string; passed: boolean; details: string }[];
  listing: { status: string; title: string; is_simulated: boolean } | null;
};

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [selected, setSelected] = useState<ProductDetail | null>(null);

  useEffect(() => {
    apiFetch<Product[]>("/products").then(setProducts).catch(() => {});
  }, []);

  async function openProduct(id: number) {
    const detail = await apiFetch<ProductDetail>(`/products/${id}`);
    setSelected(detail);
  }

  function downloadUrl(productId: number, assetId: number) {
    return `${API_BASE}/products/${productId}/assets/${assetId}/download`;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold neon-text">Product Factory</h1>
        <p className="label-dim mt-1">Real generated files, QA results, and listing readiness.</p>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="panel p-5">
          <h2 className="font-bold mb-3">Products ({products.length})</h2>
          <ul className="space-y-2">
            {products.map((p) => (
              <li
                key={p.id}
                onClick={() => openProduct(p.id)}
                className="cursor-pointer text-sm border-b border-[var(--border)] pb-2 hover:text-[var(--neon)]"
              >
                <div className="flex justify-between">
                  <span>#{p.id} {p.title}</span>
                  <span className="label-dim">{p.status}</span>
                </div>
                <div className="text-xs text-[var(--text-dim)]">
                  {p.product_type} / {p.format} -- ${p.recommended_price_usd.toFixed(2)} (margin $
                  {p.estimated_margin_usd.toFixed(2)})
                </div>
              </li>
            ))}
            {products.length === 0 && <p className="label-dim">No products generated yet. Run a mission.</p>}
          </ul>
        </div>

        <div className="panel p-5">
          <h2 className="font-bold mb-3">Details</h2>
          {!selected && <p className="label-dim">Select a product to inspect files and QA results.</p>}
          {selected && (
            <div className="space-y-4 text-sm">
              <div>
                <h3 className="font-bold mb-1">Assets</h3>
                <ul className="space-y-1">
                  {selected.assets.map((a) => (
                    <li key={a.id} className="flex justify-between">
                      <span>{a.asset_type} ({a.file_size_bytes} bytes)</span>
                      <a
                        className="text-[var(--neon)] underline"
                        href={downloadUrl(selected.id, a.id)}
                        onClick={(e) => {
                          // attach token via fetch+blob since this is an authenticated endpoint
                          e.preventDefault();
                          fetch(downloadUrl(selected.id, a.id), {
                            headers: { Authorization: `Bearer ${getToken()}` },
                          })
                            .then((r) => r.blob())
                            .then((blob) => {
                              const url = URL.createObjectURL(blob);
                              const link = document.createElement("a");
                              link.href = url;
                              link.download = `product_${selected.id}_${a.asset_type}`;
                              link.click();
                            });
                        }}
                      >
                        Download
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="font-bold mb-1">QA Results</h3>
                <ul className="space-y-1">
                  {selected.qa_results.map((r, i) => (
                    <li key={i} className={r.passed ? "text-[var(--neon)]" : "text-[var(--danger)]"}>
                      {r.passed ? "PASS" : "FAIL"} -- {r.check_name}: {r.details}
                    </li>
                  ))}
                </ul>
              </div>
              {selected.listing && (
                <div>
                  <h3 className="font-bold mb-1">Listing</h3>
                  <p>{selected.listing.title}</p>
                  <p className="label-dim">
                    status: {selected.listing.status} {selected.listing.is_simulated ? "(SIMULATED -- Etsy not connected)" : ""}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
