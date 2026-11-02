import { chatUrl } from "./chatUrl";
import { useSignals } from "@preact/signals-react/runtime";
import type { createChatsPageController } from "./ChatsPageController";
import { plainPreview, statusLabel, type RunSummary } from "./resultFormatting";
import { queuedChatEtaText, queueEtaExplanation } from "./queueStatus";

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
  const entering = model.enteringNewChatId.value === item.send_id;
  const rowStatus = item.needs_attention ? "Needs attention" : statusLabel(item.status);
  const queued = item.status === "queued" && !item.needs_attention;
  // A queued or accepted follow-up has no new answer yet: the prior answer's
  // preview must not hide the current state or the queue estimate.
  const showPreview =
    item.has_response &&
    !!item.preview.trim() &&
    !queued &&
    !(item.status === "accepted" && !item.needs_attention);
  const preview = showPreview ? plainPreview(item.preview) : "";
  const subtitle = queued ? queuedChatEtaText(item.send_id, model.queueSnapshot.value) : rowStatus;

  return (
    <div
      className={[
        "chat-entry",
        selected ? "chosen" : "",
        unread ? "unread" : "",
        entering ? "arriving" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      onAnimationEnd={(event) => {
        if (event.target === event.currentTarget && model.enteringNewChatId.peek() === item.send_id)
          model.enteringNewChatId.value = null;
      }}
    >
      <a
        href={chatUrl(item.send_id)}
        onClick={(event) => {
          if (
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
          )
            return;
          event.preventDefault();
          model.selectRun(item);
        }}
        onPointerEnter={() => model.hintRun(item.send_id)}
        onPointerLeave={() => model.cancelHintRun(item.send_id)}
        onFocus={() => void model.prefetchRun(item.send_id)}
        onPointerDown={() => void model.prefetchRun(item.send_id)}
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
        {showPreview ? (
          <span className="chat-preview" title={preview}>
            {item.needs_attention ? "Needs attention · " : ""}
            {preview}
          </span>
        ) : (
          <span
            className="chat-row-meta"
            title={queued ? queueEtaExplanation(model.queueSnapshot.value) : rowStatus}
          >
            {subtitle}
          </span>
        )}
      </a>
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
