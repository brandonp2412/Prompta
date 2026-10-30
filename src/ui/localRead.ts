// Local, read-only requests should fail visibly instead of leaving UI loading forever.
// Mutating requests use their own durable receipt/reconciliation rules.
export const localReadTimeoutMs = 12_000;

export function localGet(url: string): Promise<Response> {
  return fetch(url, {
    cache: "no-store",
    signal: AbortSignal.timeout(localReadTimeoutMs),
  });
}
