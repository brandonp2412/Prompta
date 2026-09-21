const DATABASE_NAME = "prompta-recent-chats";
const DATABASE_VERSION = 1;
const STORE_NAME = "chats";

type CachedChatRecord = {
  key: string;
  scope: string;
  conversationId: string;
  chat: any;
  accessedAt: number;
};

export class RecentChatCache {
  private readonly memory = new Map<string, any>();
  private databasePromise: Promise<IDBDatabase | null> | null = null;

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

  async remove(conversationId: string) {
    this.memory.delete(conversationId);
    const database = await this.database();
    if (!database) return;
    await new Promise<void>((resolve) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).delete(this.key(conversationId));
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

      const allRequest = store.getAll();
      allRequest.onsuccess = () => {
        const records = (allRequest.result || [])
          .filter((record: CachedChatRecord) => record.scope === this.scope)
          .sort((left: CachedChatRecord, right: CachedChatRecord) => right.accessedAt - left.accessedAt);
        for (const record of records.slice(this.limit)) store.delete(record.key);
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
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains(STORE_NAME)) {
          database.createObjectStore(STORE_NAME, { keyPath: "key" });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => resolve(null);
      request.onblocked = () => resolve(null);
    });
    return this.databasePromise;
  }
}
