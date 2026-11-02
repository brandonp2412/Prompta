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
};

export const activeToast = signal<ToastNotice | null>(null);
let nextToastId = 0;
const waitingToasts: ToastNotice[] = [];

export function notify(
  message: string,
  tone: ToastTone = "info",
  action?: ToastAction,
  duration = tone === "error" ? 6500 : 2800,
  replaceCurrent = false,
): number {
  const current = activeToast.peek();
  if (current?.message === message && current.tone === tone) return current.id;
  const waiting = waitingToasts.find(
    (notice) => notice.message === message && notice.tone === tone,
  );
  if (waiting) return waiting.id;
  const id = ++nextToastId;
  const notice = { id, message, tone, action, duration };
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
        notify(message, tone ?? "error", current.action, undefined, current.immediate);
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
