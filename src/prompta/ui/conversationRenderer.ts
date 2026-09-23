import {
  captureConversationViewport,
  restoreConversationViewport,
} from "./browserAttachments.svelte";
import { conversationState } from "./conversationState.svelte";

import { imageAttachments } from "./conversationLogic";

export function createConversationRenderer({
  onRetry,
  onBump,
  onDelete,
  onEdit,
}: {
  onRetry: (scope: string, key: string) => void;
  onBump: (key: string) => void;
  onDelete: (key: string) => void;
  onEdit: (key: string) => void;
}) {
  conversationState.onRetry = onRetry;
  conversationState.onBump = onBump;
  conversationState.onDelete = onDelete;
  conversationState.onEdit = onEdit;

  function messageNodeFingerprint(message: Record<string, any>, allowStreaming: boolean) {
    return JSON.stringify([
      message.role,
      message.status,
      message.content,
      imageAttachments(message).map((attachment) => [
        attachment.id || "",
        attachment.name || "",
        attachment.type || "",
        String(attachment.src || "").length,
      ]),
      Boolean(message.send_error),
      Boolean(message.pending_activity),
      message.pending_activity_label,
      message.retry_scope,
      message.retry_key,
      message.pending_bump_key,
      message.pending_delete_key,
      message.created_at,
      message.updated_at,
      message.display_at,
      allowStreaming,
    ]);
  }

  return {
    renderMessageNodes: async (messages: Record<string, any>[], allowStreaming: boolean) => {
      conversationState.loading = false;
      conversationState.messages = messages;
      conversationState.allowStreaming = allowStreaming;
    },
    renderLoadingState: () => {
      if (!conversationState.messages.length) conversationState.loading = true;
    },
    setPendingDeleteBusy: (deleteKey: string, busy: boolean) => {
      const deletingKeys = new Set(conversationState.deletingKeys);

      if (busy) deletingKeys.add(deleteKey);
      else deletingKeys.delete(deleteKey);

      conversationState.deletingKeys = deletingKeys;
    },
    messageNodeFingerprint,
    captureConversationViewport,
    restoreConversationViewport,
  };
}
