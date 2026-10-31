import { useSignals } from "@preact/signals-react/runtime";
import type { createChatsPageController } from "./ChatsPageController";
import { plainPreview, statusLabel, type RunSummary } from "./resultFormatting";

type Controller = ReturnType<typeof createChatsPageController>;

type Props = {
  item: RunSummary;
  model: Controller;
};

export default function ChatRow({ item, model }: Props) {
  useSignals();
  const selected = model.view.value === "chats" && model.selectedRunId.value === item.send_id;
  const unread = model.isUnread(item);
  const pinned = model.pinnedIds.value.includes(item.send_id);
  const hasPreview = item.has_response && !!item.preview.trim();
  const preview = hasPreview ? plainPreview(item.preview) : "";
  const rowStatus = item.needs_attention ? "Needs attention" : statusLabel(item.status);

  return (
    <div
      className={["chat-entry", selected ? "chosen" : "", unread ? "unread" : ""]
        .filter(Boolean)
        .join(" ")}
    >
      <button
        type="button"
        onClick={() => model.selectRun(item)}
        aria-current={selected ? "true" : undefined}
        className="chat-row"
      >
        <span className="chat-row-top">
          {unread && (
            <span title="Unread reply" className="unread-indicator">
              <span className="sr-only">Unread reply</span>
            </span>
          )}
          <strong>{item.title || "Untitled run"}</strong>
          <span
            title={rowStatus}
            className={"result-dot status-" + (item.needs_attention ? "interrupted" : item.status)}
          >
            <span className="sr-only">{rowStatus}</span>
          </span>
        </span>
        {hasPreview ? (
          <span className="chat-preview" title={preview}>
            {item.needs_attention ? "Needs attention · " : ""}
            {preview}
          </span>
        ) : (
          <span className="chat-row-meta">{rowStatus}</span>
        )}
      </button>
      <button
        type="button"
        disabled={!model.pinsReady.value}
        title={pinned ? "Unpin local chat" : "Pin local chat"}
        aria-label={(pinned ? "Unpin " : "Pin ") + item.title}
        aria-pressed={pinned}
        onClick={() => model.togglePin(item)}
        className={["chat-pin", pinned ? "active" : ""].filter(Boolean).join(" ")}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6ZM12 14v7"></path>
        </svg>
      </button>
    </div>
  );
}
