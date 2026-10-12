"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  ShieldCheck,
  Workflow,
  Rocket,
  Package,
  Store,
  Wallet,
  CheckSquare,
  Activity,
  MessageSquare,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { clearToken, getToken } from "@/lib/api";

const NAV: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/oversight", label: "Psalm 90:17 Oversight", icon: ShieldCheck },
  { href: "/agents", label: "Agent Network", icon: Workflow },
  { href: "/missions", label: "Mission Control", icon: Rocket },
  { href: "/products", label: "Product Factory", icon: Package },
  { href: "/marketplace", label: "Marketplace", icon: Store },
  { href: "/financials", label: "Financials", icon: Wallet },
  { href: "/approvals", label: "Approvals", icon: CheckSquare },
  { href: "/activity", label: "Activity", icon: Activity },
  { href: "/chat", label: "AI Chat", icon: MessageSquare },
  { href: "/settings", label: "Settings", icon: Settings },
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
        <div className="px-5 py-6">
          <div className="wordmark text-xl leading-none" style={{ color: "var(--accent-strong)" }}>
            Psalm 90:17
          </div>
          <div className="label-dim mt-1.5">Commerce OS</div>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 py-1 space-y-0.5">
          {NAV.map((item) => {
            const active = pathname?.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors border-l-2 ${
                  active
                    ? "text-[var(--text)] border-[var(--accent)] bg-[var(--surface-hover)]"
                    : "text-[var(--text-dim)] border-transparent hover:text-[var(--text)] hover:bg-[var(--surface-hover)]"
                }`}
              >
                <Icon size={16} strokeWidth={1.75} className="shrink-0" />
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
