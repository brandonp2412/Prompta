import { localGet } from "./localRead";

// An aborted local POST can commit in SQLite before the browser loses its
// response. Reconcile by read-only local state, never replay a mutation.
export async function readReceiptConfirmed(sendId: string, revision: string): Promise<boolean> {
  try {
    const response = await localGet("./api/results/" + encodeURIComponent(sendId));
    if (!response.ok) return false;
    const body: unknown = await response.json();
    return Boolean(
      body &&
      typeof body === "object" &&
      "last_read_revision" in body &&
      body.last_read_revision === revision,
    );
  } catch {
    return false;
  }
}

export async function pinReceiptConfirmed(sendId: string, pinned: boolean): Promise<boolean> {
  try {
    const response = await localGet("./api/local-chat-pins");
    if (!response.ok) return false;
    const body: unknown = await response.json();
    if (!body || typeof body !== "object" || !("items" in body) || !Array.isArray(body.items))
      return false;
    const present = body.items.some(
      (item: unknown) =>
        item && typeof item === "object" && "send_id" in item && item.send_id === sendId,
    );
    return present === pinned;
  } catch {
    return false;
  }
}
