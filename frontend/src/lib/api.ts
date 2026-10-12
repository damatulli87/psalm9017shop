const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("ultron_token");
}

export function setToken(token: string) {
  localStorage.setItem("ultron_token", token);
}

export function clearToken() {
  localStorage.removeItem("ultron_token");
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...((options.headers as Record<string, string>) || {}),
  };

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    // FastAPI error bodies are {"detail": "..."} (or a validation-error array)
    // -- surface that message directly instead of the raw JSON string.
    let message = text || res.statusText;
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed?.detail === "string") {
        message = parsed.detail;
      } else if (Array.isArray(parsed?.detail)) {
        message = parsed.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ") || message;
      }
    } catch {
      /* not JSON -- keep the raw text */
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<string> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: email, password }),
  });
  if (!res.ok) throw new ApiError(res.status, "Invalid credentials");
  const data = await res.json();
  setToken(data.access_token);
  return data.access_token;
}

export { API_BASE };
