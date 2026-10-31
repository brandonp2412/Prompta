// Local, read-only requests should fail visibly instead of leaving UI loading forever.
// Mutating requests use their own durable receipt/reconciliation rules.
export const localReadTimeoutMs = 12_000;

const transientGatewayStatuses = new Set([502, 503, 504]);
const transientRetryDelayMs = 250;

export async function localGet(url: string): Promise<Response> {
  const startedAt = Date.now();
  const first = await fetch(url, {
    cache: "no-store",
    signal: AbortSignal.timeout(localReadTimeoutMs),
  });
  if (!transientGatewayStatuses.has(first.status)) return first;
  // Only idempotent local GETs get one bounded retry. Keep the original
  // 12-second budget even when background-tab timer throttling delays us.
  if (localReadTimeoutMs - (Date.now() - startedAt) <= transientRetryDelayMs) return first;
  await new Promise<void>((resolve) => setTimeout(resolve, transientRetryDelayMs));
  const remaining = localReadTimeoutMs - (Date.now() - startedAt);
  if (remaining <= 0) return first;
  return fetch(url, {
    cache: "no-store",
    signal: AbortSignal.timeout(remaining),
  });
}
