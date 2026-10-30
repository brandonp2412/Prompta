// Bound local mutations so a stalled connection cannot trap an editor indefinitely.
// These are single attempts. Aborting the HTTP wait does NOT prove the server
// rejected a write; callers must preserve receipts or reconcile local state.
export const localMutationTimeoutMs = 30_000;
export const localUploadTimeoutMs = 60_000;

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
