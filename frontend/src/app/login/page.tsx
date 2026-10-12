"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("owner@example.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? "Invalid credentials." : "Could not reach the Psalm 90:17 API.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="panel neon-border w-full max-w-sm p-8">
        <h1 className="text-2xl font-bold neon-text tracking-widest mb-1">Psalm 90:17</h1>
        <p className="label-dim mb-6">Commerce Command Center</p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label-dim block mb-1">Owner Email</label>
            <input
              className="w-full bg-black/40 border border-[var(--border)] rounded px-3 py-2 text-sm focus:outline-none focus:border-[var(--neon-dim)]"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="label-dim block mb-1">Password</label>
            <input
              type="password"
              className="w-full bg-black/40 border border-[var(--border)] rounded px-3 py-2 text-sm focus:outline-none focus:border-[var(--neon-dim)]"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="dev default: ultron-dev-only"
            />
          </div>
          {error && <p className="text-[var(--danger)] text-sm">{error}</p>}
          <button type="submit" disabled={loading} className="btn-neon w-full">
            {loading ? "Authenticating..." : "Access Command Center"}
          </button>
        </form>
        <p className="label-dim mt-6 text-[10px] leading-relaxed">
          Dev default password is &quot;ultron-dev-only&quot; (configured in backend/app/config.py).
          Rotate it via /auth/change-password before any real deployment.
        </p>
      </div>
    </div>
  );
}
