// Bound local mutations so a stalled connection cannot trap an editor indefinitely.
// These are single attempts. Aborting the HTTP wait does NOT prove the server
// rejected a write; callers must preserve receipts or reconcile local state.
export const localMutationTimeoutMs = 30_000;
export const localUploadTimeoutMs = 60_000;

// FastAPI errors use `detail`; older local handlers used `error`. Show the
// actionable server reason for a definite 4xx rejection, but never mistake a
// transport failure or 5xx for proof that a mutation was not accepted.
export async function localRejectionDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object") {
      const detail = "detail" in body ? body.detail : null;
      const error = "error" in body ? body.error : null;
      for (const candidate of [detail, error]) {
        if (typeof candidate !== "string") continue;
        const message = candidate.trim();
        if (message && message.length <= 300) return message;
      }
    }
  } catch {
    // Some local proxies return a plain-text error page.
  }
  return fallback;
}

type LocalPostOptions = { timeoutMs?: number; signal?: AbortSignal };

export function localPost(
  url: string,
  payload: unknown,
  { timeoutMs = localMutationTimeoutMs, signal }: LocalPostOptions = {},
): Promise<Response> {
  const timeout = AbortSignal.timeout(timeoutMs);
  return fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(payload),
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  });
}
