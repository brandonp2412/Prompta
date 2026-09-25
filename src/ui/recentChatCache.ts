const SUMMARY_LIMIT = 200;

export class RecentChatCache {
  private readonly memory = new Map<string, any>();
  private summaries: any[] = [];
  private summaryFingerprint = "";

  constructor(
    _scope: string,
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
    return this.getMemory(conversationId);
  }

  remember(chat: any) {
    const conversationId = String(chat?.id || "");

    if (!conversationId) return;

    this.rememberMemory(conversationId, chat);
  }

  rememberSummaries(chats: any[]) {
    const summaries = chats.filter((chat) => String(chat?.id || "")).slice(0, SUMMARY_LIMIT);
    const fingerprint = JSON.stringify(summaries);

    if (fingerprint === this.summaryFingerprint) return false;

    this.summaries = summaries;
    this.summaryFingerprint = fingerprint;

    return true;
  }

  async warmSummaries() {
    return [...this.summaries];
  }

  async warm() {
    return [...this.memory.values()].reverse().slice(0, this.limit);
  }

  async remove(conversationId: string) {
    this.memory.delete(conversationId);

    const nextSummaries = this.summaries.filter(
      (chat) => String(chat?.id || "") !== conversationId,
    );

    if (nextSummaries.length === this.summaries.length) return;

    this.summaries = nextSummaries;
    this.summaryFingerprint = JSON.stringify(nextSummaries);
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
}
