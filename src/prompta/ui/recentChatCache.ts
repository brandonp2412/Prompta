const DATABASE_NAME = "prompta-recent-chats";

const DATABASE_VERSION = 3;

const STORE_NAME = "chats";

const ACCESSED_AT_INDEX_NAME = "scope-accessed-at";

const SUMMARY_STORE_NAME = "summaries";

const SUMMARY_LIMIT = 200;

type CachedChatRecord = {
  key: string;
  scope: string;
  conversationId: string;
  chat: any;
  accessedAt: number;
};

type CachedChatSummaryRecord = {
  key: string;
  scope: string;
  conversationId: string;
  chat: any;
  position: number;
};

export class RecentChatCache {
  private readonly memory = new Map<string, any>();
  private databasePromise: Promise<IDBDatabase | null> | null = null;
  private persistedSummaryFingerprint = "";
  private activeSummaryFingerprint = "";
  private pendingSummaryWrite: { fingerprint: string; summaries: any[] } | null = null;
  private summaryWriteRunning = false;

  constructor(
    private readonly scope: string,
    private readonly limit = 20,
  ) {}

  getMemory(conversationId: string) {
    const chat = this.memory.get(conversationId);

    if (!chat) return null;

    this.memory.delete(conversationId);
    this.memory.set(conversationId, chat);

    return chat;
  }

  async get(conversationId: string) {
    const memoryChat = this.getMemory(conversationId);

    if (memoryChat) return memoryChat;

    const database = await this.database();

    if (!database) return null;

    const record = await new Promise<CachedChatRecord | null>((resolve) => {
      const transaction = database.transaction(STORE_NAME, "readonly");
      const request = transaction.objectStore(STORE_NAME).get(this.key(conversationId));
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => resolve(null);
    });

    if (!record?.chat || record.scope !== this.scope) return null;

    this.rememberMemory(conversationId, record.chat);
    void this.persist(record.chat);

    return record.chat;
  }

  remember(chat: any) {
    const conversationId = String(chat?.id || "");

    if (!conversationId) return;

    this.rememberMemory(conversationId, chat);
    void this.persist(chat);
  }

  rememberSummaries(chats: any[]) {
    const summaries = chats.filter((chat) => String(chat?.id || "")).slice(0, SUMMARY_LIMIT);
    const fingerprint = JSON.stringify(summaries);

    if (
      fingerprint === this.persistedSummaryFingerprint ||
      fingerprint === this.activeSummaryFingerprint ||
      fingerprint === this.pendingSummaryWrite?.fingerprint
    ) {
      return false;
    }

    this.pendingSummaryWrite = { fingerprint, summaries };
    void this.drainSummaryWrites();

    return true;
  }

  async warmSummaries() {
    const database = await this.database();

    if (!database) return [];

    const records = await new Promise<CachedChatSummaryRecord[]>((resolve) => {
      const transaction = database.transaction(SUMMARY_STORE_NAME, "readonly");
      const store = transaction.objectStore(SUMMARY_STORE_NAME);
      const request = store.openCursor(this.scopeKeyRange());
      const scopedRecords: CachedChatSummaryRecord[] = [];

      request.onsuccess = () => {
        const cursor = request.result;

        if (!cursor) {
          resolve(scopedRecords);

          return;
        }

        const record = cursor.value as CachedChatSummaryRecord;

        if (record.chat) scopedRecords.push(record);

        cursor.continue();
      };
      request.onerror = () => resolve(scopedRecords);
    });

    const chats = records
      .sort((left, right) => left.position - right.position)
      .slice(0, SUMMARY_LIMIT)
      .map((record) => record.chat);
    this.persistedSummaryFingerprint = JSON.stringify(chats);

    return chats;
  }

  async warm() {
    const database = await this.database();

    if (!database) return [];

    const chats = await new Promise<any[]>((resolve) => {
      const transaction = database.transaction(STORE_NAME, "readonly");
      const store = transaction.objectStore(STORE_NAME);
      const range = IDBKeyRange.bound([this.scope, 0], [this.scope, Number.MAX_SAFE_INTEGER]);
      const request = store.index(ACCESSED_AT_INDEX_NAME).openCursor(range, "prev");
      const scopedChats: any[] = [];

      request.onsuccess = () => {
        const cursor = request.result;

        if (!cursor || scopedChats.length >= this.limit) {
          resolve(scopedChats);

          return;
        }

        const record = cursor.value as CachedChatRecord;

        if (record.chat) scopedChats.push(record.chat);

        if (scopedChats.length >= this.limit) {
          resolve(scopedChats);

          return;
        }

        cursor.continue();
      };
      request.onerror = () => resolve(scopedChats);
    });

    for (const chat of chats) {
      const conversationId = String(chat?.id || "");

      if (conversationId) this.rememberMemory(conversationId, chat);
    }

    return chats;
  }

  async remove(conversationId: string) {
    this.memory.delete(conversationId);
    const database = await this.database();

    if (!database) return;

    await new Promise<void>((resolve) => {
      const transaction = database.transaction([STORE_NAME, SUMMARY_STORE_NAME], "readwrite");
      transaction.objectStore(STORE_NAME).delete(this.key(conversationId));
      transaction.objectStore(SUMMARY_STORE_NAME).delete(this.key(conversationId));
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => resolve();
      transaction.onabort = () => resolve();
    });
  }

  private rememberMemory(conversationId: string, chat: any) {
    this.memory.delete(conversationId);
    this.memory.set(conversationId, chat);

    while (this.memory.size > this.limit) {
      const oldest = this.memory.keys().next().value;

      if (!oldest) break;

      this.memory.delete(oldest);
    }
  }

  private key(conversationId: string) {
    return this.scope + ":" + conversationId;
  }

  private scopeKeyRange() {
    const prefix = this.scope + ":";

    return IDBKeyRange.bound(prefix, prefix + "￿");
  }

  private async persist(chat: any) {
    const conversationId = String(chat?.id || "");

    if (!conversationId) return;

    const database = await this.database();

    if (!database) return;

    await new Promise<void>((resolve) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      const store = transaction.objectStore(STORE_NAME);
      store.put({
        key: this.key(conversationId),
        scope: this.scope,
        conversationId,
        chat,
        accessedAt: Date.now(),
      } satisfies CachedChatRecord);

      const range = IDBKeyRange.bound([this.scope, 0], [this.scope, Number.MAX_SAFE_INTEGER]);
      const cursorRequest = store.index(ACCESSED_AT_INDEX_NAME).openKeyCursor(range, "prev");
      let retained = 0;

      cursorRequest.onsuccess = () => {
        const cursor = cursorRequest.result;

        if (!cursor) return;

        retained += 1;

        if (retained > this.limit) store.delete(cursor.primaryKey);

        cursor.continue();
      };
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => resolve();
      transaction.onabort = () => resolve();
    });
  }

  private async drainSummaryWrites() {
    if (this.summaryWriteRunning) return;

    this.summaryWriteRunning = true;

    try {
      while (this.pendingSummaryWrite) {
        const pending = this.pendingSummaryWrite;
        this.pendingSummaryWrite = null;

        if (pending.fingerprint === this.persistedSummaryFingerprint) continue;

        this.activeSummaryFingerprint = pending.fingerprint;
        await this.persistSummaries(pending.summaries);
        this.persistedSummaryFingerprint = pending.fingerprint;
        this.activeSummaryFingerprint = "";
      }
    } finally {
      this.activeSummaryFingerprint = "";
      this.summaryWriteRunning = false;

      if (this.pendingSummaryWrite) void this.drainSummaryWrites();
    }
  }

  private async persistSummaries(chats: any[]) {
    const database = await this.database();

    if (!database) return;

    const retainedIds = new Set(chats.map((chat) => String(chat.id)));

    await new Promise<void>((resolve) => {
      const transaction = database.transaction(SUMMARY_STORE_NAME, "readwrite");
      const store = transaction.objectStore(SUMMARY_STORE_NAME);
      const cursorRequest = store.openCursor(this.scopeKeyRange());
      cursorRequest.onsuccess = () => {
        const cursor = cursorRequest.result;

        if (cursor) {
          const record = cursor.value as CachedChatSummaryRecord;

          if (!retainedIds.has(String(record.conversationId || ""))) cursor.delete();

          cursor.continue();

          return;
        }

        chats.forEach((chat, position) => {
          const conversationId = String(chat.id);
          store.put({
            key: this.key(conversationId),
            scope: this.scope,
            conversationId,
            chat,
            position,
          } satisfies CachedChatSummaryRecord);
        });
      };
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => resolve();
      transaction.onabort = () => resolve();
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

      request.onupgradeneeded = (event) => {
        const database = request.result;
        const transaction = request.transaction;
        const chatStore = database.objectStoreNames.contains(STORE_NAME)
          ? transaction?.objectStore(STORE_NAME)
          : database.createObjectStore(STORE_NAME, { keyPath: "key" });

        if (chatStore && !chatStore.indexNames.contains(ACCESSED_AT_INDEX_NAME)) {
          chatStore.createIndex(ACCESSED_AT_INDEX_NAME, ["scope", "accessedAt"]);
        }

        if (chatStore && event.oldVersion > 0 && event.oldVersion < DATABASE_VERSION) {
          chatStore.clear();
        }

        if (!database.objectStoreNames.contains(SUMMARY_STORE_NAME)) {
          database.createObjectStore(SUMMARY_STORE_NAME, { keyPath: "key" });
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
