import { useEffect } from "react";
import { useSignals } from "@preact/signals-react/runtime";
import { activeToast, dismissToast } from "./toast";

export default function ToastHost({ chatView }: { chatView: boolean }) {
  useSignals();
  const notice = activeToast.value;
  let symbol = "i";
  if (notice?.tone === "success") symbol = "✓";
  else if (notice?.tone === "error") symbol = "!";
  useEffect(() => {
    if (!notice || notice.duration === 0) return;
    const timer = setTimeout(() => dismissToast(notice.id), notice.duration);
    return () => clearTimeout(timer);
  }, [notice]);

  return (
    <div className={"toast-viewport" + (chatView ? " chat-view" : "")}>
      {notice && (
        <div
          key={notice.id}
          className={"toast-card " + notice.tone}
          role={notice.tone === "error" ? "alert" : "status"}
          aria-live={notice.tone === "error" ? "assertive" : "polite"}
        >
          <span className="toast-symbol" aria-hidden="true">
            {symbol}
          </span>
          <span className="toast-message">{notice.message}</span>
          {notice.action && (
            <button
              type="button"
              className="toast-action"
              onClick={() => {
                dismissToast(notice.id);
                notice.action?.onClick();
              }}
            >
              {notice.action.label}
            </button>
          )}
          <button
            type="button"
            className="toast-close"
            aria-label="Dismiss notification"
            onClick={() => dismissToast(notice.id)}
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}
