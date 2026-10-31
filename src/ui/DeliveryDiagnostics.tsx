import { useSignals } from "@preact/signals-react/runtime";
import type { createJobsPageController } from "./JobsPageController";
import { formatDate } from "./jobView";

type Controller = ReturnType<typeof createJobsPageController>;

export default function DeliveryDiagnostics({ model }: { model: Controller }) {
  useSignals();
  const health = model.deliveryHealth.value;
  const error = model.deliveryHealthError.value;
  const pause = Math.max(
    health?.recovery.account_read_backoff_seconds ?? 0,
    health?.recovery.security_pause_seconds ?? 0,
  );
  const pace = health?.recovery.global_pace_seconds ?? 0;
  const nextRetry = health?.queue.next_retry_at_epoch;
  const attentionCount = health?.recovery.attention_chats ?? 0;
  const recoveryWaiting = Boolean(
    health &&
    pause > 0 &&
    (health.recovery.recoverable > 0 || health.recovery.recoverable_reply_captures > 0),
  );

  let label = !health && !error ? "loading…" : "status unavailable";
  if (!error && health?.ready === false) label = "needs attention";
  else if (!error && health?.admission?.blocked) label = "waiting for capacity";
  else if (!error && health) label = attentionCount > 0 ? "online · review needed" : "online";

  return (
    <details className="delivery-diagnostics">
      <summary>
        <span
          className={
            error || health?.ready === false || health?.admission?.blocked || attentionCount > 0
              ? "delivery-indicator degraded"
              : "delivery-indicator"
          }
        ></span>
        Delivery {label}
        {health && (
          <>
            <span className="delivery-count">{model.pendingDeliveries.value} pending</span>
            {attentionCount > 0 && (
              <span className="delivery-count">
                {attentionCount} {attentionCount === 1 ? "chat needs" : "chats need"} review
              </span>
            )}
            {health.queue.outcome_unknown > 0 && (
              <span className="delivery-count">
                {health.queue.outcome_unknown} unconfirmed historically
              </span>
            )}
            {recoveryWaiting && <span className="delivery-count">Recovery paused</span>}
          </>
        )}
      </summary>
      {error && (
        <p role="alert">
          {error}{" "}
          <button type="button" onClick={() => void model.loadDeliveryHealth()}>
            Retry
          </button>
        </p>
      )}
      {health && (
        <>
          {error && <p>Showing last known status.</p>}
          {health.issues.length > 0 && <p role="status">{health.issues.join(" · ")}</p>}
          {health.admission?.blocked && (
            <p role="status">
              Dispatch paused:{" "}
              {health.admission.reason || "Host resource admission is blocking new sends"}.
            </p>
          )}
          <dl>
            <div>
              <dt>Queued</dt>
              <dd>{health.queue.queued}</dd>
            </div>
            <div>
              <dt>Running</dt>
              <dd>{health.queue.running}</dd>
            </div>
            <div>
              <dt>Retrying</dt>
              <dd>{health.queue.retrying}</dd>
            </div>
            <div>
              <dt>Rate limited</dt>
              <dd>{health.queue.rate_limited}</dd>
            </div>
            {nextRetry !== undefined && nextRetry !== 0 && (
              <div>
                <dt>Next queued retry</dt>
                <dd>{formatDate(nextRetry)}</dd>
              </div>
            )}
            <div>
              <dt>Dead letters</dt>
              <dd>{health.queue.dead_lettered}</dd>
            </div>
            <div>
              <dt>Unconfirmed sends</dt>
              <dd>{health.queue.outcome_unknown}</dd>
            </div>
          </dl>
          <dl>
            <div>
              <dt>Captures in progress</dt>
              <dd>{health.recovery.active_captures}</dd>
            </div>
            <div>
              <dt>Stale capture leases</dt>
              <dd>{health.recovery.stale_capture_leases}</dd>
            </div>
            <div>
              <dt>Chats eligible for read-only recovery</dt>
              <dd>{health.recovery.recoverable}</dd>
            </div>
            <div>
              <dt>Per-chat probes due (subject to cooldown)</dt>
              <dd>{health.recovery.ready_for_read_only_probe}</dd>
            </div>
            <div>
              <dt>Unresolved follow-up captures</dt>
              <dd>{health.recovery.unresolved_reply_captures}</dd>
            </div>
            <div>
              <dt>Follow-ups eligible for recovery</dt>
              <dd>{health.recovery.recoverable_reply_captures}</dd>
            </div>
            <div>
              <dt>Due follow-up probes</dt>
              <dd>{health.recovery.due_reply_recovery_probes}</dd>
            </div>
            <div>
              <dt>Missing verified chat identity</dt>
              <dd>{health.recovery.missing_verified_identity}</dd>
            </div>
            <div>
              <dt>Chats needing attention</dt>
              <dd>{attentionCount}</dd>
            </div>
          </dl>
          {health.recovery.stale_capture_leases > 0 && (
            <p role="status">Capture overdue; recovery pending.</p>
          )}
          {recoveryWaiting && (
            <p role="status">Recovery paused · {Math.ceil(pause / 60)} min remaining.</p>
          )}
          {!recoveryWaiting && pace > 0 && health.recovery.ready_for_read_only_probe > 0 && (
            <p>Next recovery check in {Math.ceil(pace)} seconds.</p>
          )}
          {health.recovery.missing_verified_identity > 0 && (
            <p>Automatic recovery unavailable for chats without a verified ID.</p>
          )}
          {(health.queue.retrying > 0 || health.queue.rate_limited > 0) && (
            <p>Retries scheduled automatically.</p>
          )}
          {health.queue.outcome_unknown > 0 && <p>Check unconfirmed sends before sending again.</p>}
        </>
      )}
    </details>
  );
}
