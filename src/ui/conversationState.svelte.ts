type Message = Record<string, any>;

export class ConversationState {
  progress = $state.raw<import("./chatProgress").ChatProgress | null>(null);
  messages = $state.raw<Message[]>([]);
  allowStreaming = $state(false);
  loading = $state(false);
  deletingKeys = $state.raw(new Set<string>());
  onRetry: (scope: string, key: string) => void = () => {};
  onBump: (key: string) => void = () => {};
  onDelete: (key: string) => void = () => {};
  onEdit: (key: string) => void = () => {};
}

export const conversationState = new ConversationState();
