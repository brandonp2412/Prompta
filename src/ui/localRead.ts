// Local, read-only requests should fail visibly instead of leaving UI loading forever.
// Mutating requests use their own durable receipt/reconciliation rules.
export const localReadTimeoutMs = 12_000;

const transientGatewayStatuses = new Set([502, 503, 504]);
const transientRetryDelayMs = 250;
const firstAttemptTimeoutMs = 6000;

export async function localGet(url: string): Promise<Response> {
  const startedAt = Date.now();
  const request = (timeoutMs: number) =>
    fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });

  // A hung gateway must not consume the entire read budget. The second GET is
  // safe (no mutation) and can recover from an intermittent transport failure.
  let response: Response | undefined;
  let failure: unknown;
  try {
    response = await request(firstAttemptTimeoutMs);
  } catch (error) {
    failure = error;
  }
  if (response && !transientGatewayStatuses.has(response.status)) return response;
  const remainingBeforeDelay = localReadTimeoutMs - (Date.now() - startedAt);
  if (remainingBeforeDelay <= transientRetryDelayMs) {
    if (response) return response;
    throw failure;
  }
  await new Promise<void>((resolve) => setTimeout(resolve, transientRetryDelayMs));
  const remaining = localReadTimeoutMs - (Date.now() - startedAt);
  if (remaining <= 0) {
    if (response) return response;
    throw failure;
  }
  return request(remaining);
}
