import { useSignals } from "@preact/signals-react/runtime";
import type { createJobsPageController } from "./JobsPageController";

type Controller = ReturnType<typeof createJobsPageController>;

export default function DeliveryDiagnostics({ model }: { model: Controller }) {
  useSignals();
  const health = model.deliveryHealth.value;
  const error = model.deliveryHealthError.value;
  const pause = model.recoveryPauseSeconds.value;
  const nextRetry = health?.queue.next_retry_at_epoch;
  const recoveryWaiting = Boolean(
    health &&
    pause > 0 &&
    (health.recovery.recoverable > 0 || health.recovery.recoverable_reply_captures > 0),
  );

  let label = "status unavailable";
  if (!error && health?.ready === false) label = "needs attention";
  else if (!error && health?.admission?.blocked) label = "waiting for capacity";
  else if (!error && health) label = "online";

  if (!health && !error) return null;

  return (
    <details className="delivery-diagnostics">
      <summary>
        <span
          className={
            error || health?.ready === false || health?.admission?.blocked
              ? "delivery-indicator degraded"
              : "delivery-indicator"
          }
        ></span>
        Delivery {label}
        {health && (
          <>
            <span className="delivery-count">{model.pendingDeliveries.value} pending</span>
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
          {error && (
            <p>Counts below are from the last successful check, not current service status.</p>
          )}
          {health.issues.length ? (
            <p role="status">{health.issues.join(" · ")}</p>
          ) : (
            !error && <p>UI, scheduler, delivery worker and browser are responding.</p>
          )}
          {health.admission?.blocked && (
            <p role="status">
              Dispatch paused:{" "}
              {health.admission.reason || "Host resource admission is blocking new sends"}. Queued
              jobs are retained until capacity returns; no sends are retried after an uncertain
              outcome.
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
                <dd>{model.formatDate(nextRetry)}</dd>
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
              <dt>Due for recovery probe</dt>
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
          </dl>
          {health.recovery.stale_capture_leases > 0 && (
            <p role="status">
              A capture lease is overdue. The worker will reconcile it as interrupted before
              read-only recovery; the original send is never replayed.
            </p>
          )}
          {recoveryWaiting && (
            <p role="status">
              Read-only recovery is waiting for the account safety cooldown (about{" "}
              {Math.ceil(pause / 60)} min). No automatic resends will occur.
            </p>
          )}
          {!recoveryWaiting &&
            health.recovery.global_pace_seconds > 0 &&
            health.recovery.ready_for_read_only_probe > 0 && (
              <p>
                Read-only recovery is paced to one verified chat at a time; next probe in about{" "}
                {Math.ceil(health.recovery.global_pace_seconds)} seconds.
              </p>
            )}
          {health.recovery.missing_verified_identity > 0 && (
            <p>
              Chats without a verified conversation identity cannot be recovered automatically.
              Their local partial results remain available.
            </p>
          )}
          {(health.queue.retrying > 0 || health.queue.rate_limited > 0) && (
            <p>Rejected or pre-dispatch attempts retry automatically after their backoff.</p>
          )}
          {health.queue.outcome_unknown > 0 && (
            <p>
              Unconfirmed sends are not automatically retried. Review the exact saved chat before
              sending again.
            </p>
          )}
        </>
      )}
    </details>
  );
}
