/** Thin fetch wrapper for the Flowcept API under /api/v1. */

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

async function handle<T>(rs: Response): Promise<T> {
  if (!rs.ok) {
    let detail = rs.statusText;
    try {
      const body = await rs.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(rs.status, detail);
  }
  return rs.json() as Promise<T>;
}

export async function apiGet<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const url = new URL(API_BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
  }
  return handle<T>(await fetch(url));
}

export async function apiSend<T>(method: string, path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(API_BASE + path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

export const apiPost = <T>(path: string, body?: unknown) => apiSend<T>("POST", path, body);
export const apiPut = <T>(path: string, body?: unknown) => apiSend<T>("PUT", path, body);
export const apiDelete = <T>(path: string) => apiSend<T>("DELETE", path);

export async function apiGetText(path: string, params?: Record<string, string>): Promise<string> {
  const url = new URL(API_BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(params ?? {})) url.searchParams.set(k, v);
  const rs = await fetch(url);
  if (!rs.ok) throw new ApiError(rs.status, rs.statusText);
  return rs.text();
}
