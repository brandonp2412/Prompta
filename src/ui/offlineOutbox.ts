const DATABASE_NAME = "prompta-offline-outbox";
const DATABASE_VERSION = 1;
const STORE_NAME = "posts";
const CREATED_AT_INDEX_NAME = "scope-created-at";

export type OfflinePostOperation = "new_chat" | "reply";

export type OfflinePostAttachment = {
  name: string;
  type: string;
  data: string;
};

export type OfflinePostInput = {
  operation: OfflinePostOperation;
  targetChatId?: string | null;
  message: string;
  attachments?: OfflinePostAttachment[];
  clientId: string;
  createdAt?: number;
  lastError?: string;
};

export type OfflinePostRecord = {
  id: string;
  scope: string;
  operation: OfflinePostOperation;
  targetChatId: string | null;
  message: string;
  attachments: OfflinePostAttachment[];
  clientId: string;
  createdAt: number;
  retryState: "pending";
  retryCount: number;
  lastAttemptAt: number | null;
  lastError: string;
};

export type OfflineOutboxWriter = {
  put(record: OfflinePostRecord): Promise<void>;
};

class IndexedDbOfflineOutboxWriter implements OfflineOutboxWriter {
  private databasePromise: Promise<IDBDatabase | null> | null = null;

  async put(record: OfflinePostRecord) {
    const database = await this.database();

    if (!database) throw new Error("IndexedDB is unavailable");

    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).put(record);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () =>
        reject(transaction.error || new Error("Offline outbox write failed"));
      transaction.onabort = () =>
        reject(transaction.error || new Error("Offline outbox write aborted"));
    });
  }

  private database() {
    if (this.databasePromise) return this.databasePromise;

    this.databasePromise = new Promise((resolve) => {
      if (!("indexedDB" in globalThis)) {
        resolve(null);

        return;
      }

      let request: IDBOpenDBRequest;

      try {
        request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
      } catch {
        resolve(null);

        return;
      }

      request.onupgradeneeded = () => {
        const database = request.result;
        const store = database.objectStoreNames.contains(STORE_NAME)
          ? request.transaction?.objectStore(STORE_NAME)
          : database.createObjectStore(STORE_NAME, { keyPath: "id" });

        if (store && !store.indexNames.contains(CREATED_AT_INDEX_NAME)) {
          store.createIndex(CREATED_AT_INDEX_NAME, ["scope", "createdAt"]);
        }
      };
      request.onsuccess = () => {
        const database = request.result;
        database.onversionchange = () => database.close();
        resolve(database);
      };
      request.onerror = () => resolve(null);
    });

    return this.databasePromise;
  }
}

export function createOfflinePostRecord(
  scope: string,
  input: OfflinePostInput,
  createdAt = Date.now(),
): OfflinePostRecord {
  const clientId = input.clientId.trim();

  if (!clientId) throw new Error("Offline outbox requires a client id");

  return {
    id: `${scope}:${clientId}`,
    scope,
    operation: input.operation,
    targetChatId: input.targetChatId?.trim() || null,
    message: input.message,
    attachments: (input.attachments || []).map((attachment) => ({ ...attachment })),
    clientId,
    createdAt: input.createdAt ?? createdAt,
    retryState: "pending",
    retryCount: 0,
    lastAttemptAt: null,
    lastError: input.lastError || "",
  };
}

export class OfflineOutbox {
  constructor(
    private readonly scope: string,
    private readonly writer: OfflineOutboxWriter = new IndexedDbOfflineOutboxWriter(),
  ) {}

  async enqueue(input: OfflinePostInput) {
    const record = createOfflinePostRecord(this.scope, input);
    await this.writer.put(record);

    return record;
  }
}
