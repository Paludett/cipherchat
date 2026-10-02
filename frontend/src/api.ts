const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
export const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws";

export class ApiError extends Error {
  code: string;
  retryAfter: number | null; 

  constructor(code: string, message = "", retryAfter: number | null = null) {
    super(message);
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

type Options = { method?: string; body?: unknown; token?: string | null };

export async function request<T>(path: string, { method = "GET", body, token }: Options = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("network_error");
  }

  if (res.status === 204) return undefined as T;

  // Resposta sem JSON (ex.: 502) cai no fallback abaixo
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const retryAfter = Number(res.headers.get("Retry-After")) || null;
    throw new ApiError(data?.error?.code ?? "internal_error", data?.error?.message ?? "", retryAfter);
  }
  return data as T;
}
