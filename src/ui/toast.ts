import { effect, signal, type ReadonlySignal } from "@preact/signals-core";
import { useEffect, useRef } from "react";

export type ToastTone = "error" | "warning" | "success" | "info";
type ToastAction = { label: string; onClick: () => void };
export type ToastNotice = {
  id: number;
  message: string;
  tone: ToastTone;
  action?: ToastAction;
  duration: number;
  outageSensitive?: boolean;
};

export const activeToast = signal<ToastNotice | null>(null);
let nextToastId = 0;
const waitingToasts: ToastNotice[] = [];
const outageMessage = "Connection to Prompta interrupted. Reconnecting automatically.";
const readRecoveryGraceMs = 8000;
let readUnavailable = false;
let streamDelayed = false;
let outageNotified = false;
let outageToastId: number | null = null;
let recoveryTimer: ReturnType<typeof setTimeout> | undefined;

function clearRecoveryTimer() {
  if (recoveryTimer !== undefined) clearTimeout(recoveryTimer);
  recoveryTimer = undefined;
}

function showOutage() {
  if (outageNotified) return;
  outageNotified = true;
  // These all describe the same unavailable backend, not separate errors.
  for (let i = waitingToasts.length - 1; i >= 0; i--) {
    if (waitingToasts[i]?.outageSensitive) waitingToasts.splice(i, 1);
  }
  outageToastId = notify(outageMessage, "warning", undefined, 0, true);
}

function clearOutageIfHealthy() {
  if (readUnavailable || streamDelayed || !outageNotified) return;
  outageNotified = false;
  if (outageToastId !== null) dismissToast(outageToastId);
  outageToastId = null;
}

export function reportBackendReadFailure() {
  clearRecoveryTimer();
  readUnavailable = true;
  showOutage();
}

export function reportBackendReadSuccess() {
  if (!readUnavailable) return;
  clearRecoveryTimer();
  // A single successful request during a rolling deploy does not mean that
  // the rest of the API is available. Require a short quiet recovery window.
  recoveryTimer = setTimeout(() => {
    recoveryTimer = undefined;
    readUnavailable = false;
    clearOutageIfHealthy();
  }, readRecoveryGraceMs);
}

export function setLiveStreamDelayed(delayed: boolean) {
  streamDelayed = delayed;
  if (delayed) showOutage();
  else clearOutageIfHealthy();
}

export function resetBackendOutage() {
  clearRecoveryTimer();
  readUnavailable = false;
  streamDelayed = false;
  clearOutageIfHealthy();
}

export function notify(
  message: string,
  tone: ToastTone = "info",
  action?: ToastAction,
  duration = tone === "error" ? 6500 : 2800,
  replaceCurrent = false,
  outageSensitive = false,
): number {
  if (outageNotified && outageSensitive) return outageToastId ?? 0;
  const current = activeToast.peek();
  if (current?.message === message && current.tone === tone) return current.id;
  const waiting = waitingToasts.find(
    (notice) => notice.message === message && notice.tone === tone,
  );
  if (waiting) return waiting.id;
  const id = ++nextToastId;
  const notice = { id, message, tone, action, duration, outageSensitive };
  if (!current) activeToast.value = notice;
  else if (tone === "success" || tone === "info") {
    // Direct user feedback (such as Copy) must appear immediately.
    activeToast.value = notice;
  } else if (replaceCurrent || (tone === "error" && current.tone !== "error")) {
    if (!replaceCurrent && current.duration > 0) waitingToasts.unshift(current);
    activeToast.value = notice;
  } else {
    waitingToasts.push(notice);
    if (waitingToasts.length > 4) waitingToasts.shift();
  }
  return id;
}

export function dismissToast(id: number): void {
  if (activeToast.peek()?.id === id) {
    activeToast.value = waitingToasts.shift() ?? null;
    return;
  }
  const index = waitingToasts.findIndex((notice) => notice.id === id);
  if (index !== -1) waitingToasts.splice(index, 1);
}

type SignalToastOptions = {
  tone?: ToastTone | ((message: string) => ToastTone);
  when?: (message: string) => boolean;
  action?: ToastAction;
  immediate?: boolean;
  outageSensitive?: boolean;
};

export function useToastSignal(
  source: ReadonlySignal<string>,
  options: SignalToastOptions = {},
): void {
  const optionsRef = useRef(options);
  optionsRef.current = options;
  useEffect(
    () =>
      effect(() => {
        const message = source.value;
        if (!message) return;
        const current = optionsRef.current;
        if (current.when && !current.when(message)) return;
        const tone = typeof current.tone === "function" ? current.tone(message) : current.tone;
        notify(
          message,
          tone ?? "error",
          current.action,
          undefined,
          current.immediate,
          current.outageSensitive,
        );
      }),
    [source],
  );
}

export function feedbackTone(message: string): ToastTone {
  return /failed|could not|cannot|unavailable|invalid|rejected|uncertain|nothing was sent|not sent|too large|blocked|unable/i.test(
    message,
  )
    ? "error"
    : "success";
}
