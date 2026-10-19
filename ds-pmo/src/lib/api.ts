/**
 * Centralized fetch utility with consistent error handling.
 * Throws a typed ApiError on non-2xx responses.
 */

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    let message = `Request failed: ${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.error) message = body.error;
    } catch {
      // ignore parse error
    }
    throw new ApiError(message, res.status);
  }

  // 204 No Content — return undefined cast
  if (res.status === 204) return undefined as T;

  return res.json() as Promise<T>;
}

type RequestOpts = { signal?: AbortSignal };

export const api = {
  get: <T>(url: string, opts?: RequestOpts) =>
    request<T>(url, { signal: opts?.signal }),
  post: <T>(url: string, body: unknown, opts?: RequestOpts) =>
    request<T>(url, { method: "POST", body: JSON.stringify(body), signal: opts?.signal }),
  put: <T>(url: string, body: unknown, opts?: RequestOpts) =>
    request<T>(url, { method: "PUT", body: JSON.stringify(body), signal: opts?.signal }),
  patch: <T>(url: string, body: unknown, opts?: RequestOpts) =>
    request<T>(url, { method: "PATCH", body: JSON.stringify(body), signal: opts?.signal }),
  delete: <T>(url: string, opts?: RequestOpts) =>
    request<T>(url, { method: "DELETE", signal: opts?.signal }),
};
