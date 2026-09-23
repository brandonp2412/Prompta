const DATABASE_NAME = "prompta-recent-chats";

const DATABASE_VERSION = 4;

const STORE_NAME = "chats";

const ACCESSED_AT_INDEX_NAME = "scope-accessed-at";

const SUMMARY_POSITION_INDEX_NAME = "scope-position";

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
  private readonly pendingChats = new Map<string, any>();
  private databasePromise: Promise<IDBDatabase | null> | null = null;
  private persistTimer: ReturnType<typeof setTimeout> | null = null;
  private summariesTimer: ReturnType<typeof setTimeout> | null = null;
  private pendingSummaries: any[] | null = null;

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
    this.schedulePersist(record.chat);

    return record.chat;
  }

  remember(chat: any) {
    const conversationId = String(chat?.id || "");

    if (!conversationId) return;

    this.rememberMemory(conversationId, chat);
    this.schedulePersist(chat);
  }

  rememberSummaries(chats: any[]) {
    const summaries = chats.filter((chat) => String(chat?.id || "")).slice(0, SUMMARY_LIMIT);
    this.pendingSummaries = summaries;

    if (this.summariesTimer !== null) return;

    this.summariesTimer = setTimeout(() => {
      this.summariesTimer = null;
      const pending = this.pendingSummaries;
      this.pendingSummaries = null;

      if (pending) void this.persistSummaries(pending);
    }, 200);
  }

  async warmSummaries() {
    const database = await this.database();

    if (!database) return [];

    const records = await new Promise<CachedChatSummaryRecord[]>((resolve) => {
      const transaction = database.transaction(SUMMARY_STORE_NAME, "readonly");
      const store = transaction.objectStore(SUMMARY_STORE_NAME);
      const index = store.index(SUMMARY_POSITION_INDEX_NAME);
      const range = IDBKeyRange.bound([this.scope, 0], [this.scope, Number.MAX_SAFE_INTEGER]);
      const request = index.openCursor(range);
      const result: CachedChatSummaryRecord[] = [];

      request.onsuccess = () => {
        const cursor = request.result;

        if (!cursor || result.length >= SUMMARY_LIMIT) {
          resolve(result);

          return;
        }

        result.push(cursor.value);
        cursor.continue();
      };
      request.onerror = () => resolve([]);
    });

    return records.filter((record) => record.chat).map((record) => record.chat);
  }

  async warm() {
    const database = await this.database();

    if (!database) return [];

    const records = await new Promise<CachedChatRecord[]>((resolve) => {
      const transaction = database.transaction(STORE_NAME, "readonly");
      const store = transaction.objectStore(STORE_NAME);
      const index = store.index(ACCESSED_AT_INDEX_NAME);
      const range = IDBKeyRange.bound([this.scope, 0], [this.scope, Number.MAX_SAFE_INTEGER]);
      const request = index.openCursor(range, "prev");
      const result: CachedChatRecord[] = [];

      request.onsuccess = () => {
        const cursor = request.result;

        if (!cursor || result.length >= this.limit) {
          resolve(result);

          return;
        }

        result.push(cursor.value);
        cursor.continue();
      };
      request.onerror = () => resolve([]);
    });
    const chats = records.filter((record) => record.chat).map((record) => record.chat);

    for (const chat of chats) {
      const conversationId = String(chat?.id || "");

      if (conversationId) this.rememberMemory(conversationId, chat);
    }

    return chats;
  }

  async remove(conversationId: string) {
    this.memory.delete(conversationId);
    this.pendingChats.delete(conversationId);
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

  private schedulePersist(chat: any) {
    const conversationId = String(chat?.id || "");

    if (!conversationId) return;

    this.pendingChats.set(conversationId, chat);

    if (this.persistTimer !== null) return;

    this.persistTimer = setTimeout(() => {
      this.persistTimer = null;
      const pending = [...this.pendingChats.values()];
      this.pendingChats.clear();
      void this.persistMany(pending);
    }, 120);
  }

  private async persistMany(chats: any[]) {
    if (!chats.length) return;

    const database = await this.database();

    if (!database) return;

    await new Promise<void>((resolve) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      const store = transaction.objectStore(STORE_NAME);
      const accessedAt = Date.now();

      for (const chat of chats) {
        const conversationId = String(chat?.id || "");

        if (!conversationId) continue;

        store.put({
          key: this.key(conversationId),
          scope: this.scope,
          conversationId,
          chat,
          accessedAt,
        } satisfies CachedChatRecord);
      }

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

  private async persistSummaries(chats: any[]) {
    const database = await this.database();

    if (!database) return;

    const retainedIds = new Set(chats.map((chat) => String(chat.id)));

    await new Promise<void>((resolve) => {
      const transaction = database.transaction(SUMMARY_STORE_NAME, "readwrite");
      const store = transaction.objectStore(SUMMARY_STORE_NAME);
      const range = IDBKeyRange.bound([this.scope, 0], [this.scope, Number.MAX_SAFE_INTEGER]);
      const cursorRequest = store.index(SUMMARY_POSITION_INDEX_NAME).openCursor(range);

      cursorRequest.onsuccess = () => {
        const cursor = cursorRequest.result;

        if (!cursor) return;

        const record = cursor.value as CachedChatSummaryRecord;

        if (!retainedIds.has(String(record.conversationId || ""))) cursor.delete();

        cursor.continue();
      };

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

        const summaryStore = database.objectStoreNames.contains(SUMMARY_STORE_NAME)
          ? transaction?.objectStore(SUMMARY_STORE_NAME)
          : database.createObjectStore(SUMMARY_STORE_NAME, { keyPath: "key" });

        if (summaryStore && !summaryStore.indexNames.contains(SUMMARY_POSITION_INDEX_NAME)) {
          summaryStore.createIndex(SUMMARY_POSITION_INDEX_NAME, ["scope", "position"]);
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
