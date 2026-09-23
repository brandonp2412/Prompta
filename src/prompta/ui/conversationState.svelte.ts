type Message = Record<string, any>;

export class ConversationState {
  messages = $state.raw<Message[]>([]);
  allowStreaming = $state(false);
  loading = $state(false);
  deletingKeys = $state.raw(new Set<string>());
  onRetry: (scope: string, key: string) => void = () => {};
  onDelete: (key: string) => void = () => {};
  onEdit: (key: string) => void = () => {};
}

export const conversationState = new ConversationState();
