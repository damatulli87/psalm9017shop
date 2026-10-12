"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken, getToken } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Dashboard", glyph: "\u{1F4CA}" },
  { href: "/oversight", label: "ULTRON Oversight", glyph: "\u{1F6E1}️" },
  { href: "/agents", label: "Agent Network", glyph: "\u{1F9E9}" },
  { href: "/missions", label: "Mission Control", glyph: "\u{1F680}" },
  { href: "/products", label: "Product Factory", glyph: "\u{1F4E6}" },
  { href: "/marketplace", label: "Marketplace", glyph: "\u{1F6D2}" },
  { href: "/financials", label: "Financials", glyph: "\u{1F4B0}" },
  { href: "/approvals", label: "Approvals", glyph: "✅" },
  { href: "/activity", label: "Activity", glyph: "\u{1F4E1}" },
  { href: "/chat", label: "AI Chat", glyph: "\u{1F4AC}" },
  { href: "/settings", label: "Settings", glyph: "⚙️" },
];

export default function HQLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
    } else {
      setReady(true);
    }
  }, [router]);

  if (!ready) return null;

  return (
    <div className="flex flex-1 min-h-screen">
      <aside className="w-64 bg-[var(--surface)] border-r border-[var(--border-soft)] flex flex-col shrink-0">
        <div className="p-5 flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center font-bold text-sm shrink-0"
            style={{ background: "linear-gradient(135deg, var(--accent) 0%, var(--blue) 100%)", color: "#06160f" }}
          >
            U
          </div>
          <div>
            <div className="text-base font-bold tracking-tight">ULTRON</div>
            <div className="label-dim">Commerce OS</div>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 py-2 space-y-0.5">
          {NAV.map((item) => {
            const active = pathname?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                  active
                    ? "bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                    : "text-[var(--text-dim)] hover:text-[var(--text)] hover:bg-[var(--surface-hover)]"
                }`}
              >
                <span className="w-5 text-center text-base">{item.glyph}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="p-3 border-t border-[var(--border-soft)]">
          <button
            className="btn-danger w-full text-xs"
            onClick={() => {
              clearToken();
              router.push("/login");
            }}
          >
            Sign Out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto p-7">{children}</main>
    </div>
  );
}
