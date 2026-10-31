import { expect, test } from "bun:test";
import { createChatComposerController } from "../src/ui/ChatComposerController";
import {
  clearComposerDraft,
  readComposerDraft,
  rememberComposerDraft,
} from "../src/ui/composerDraftMemory";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((finish) => {
    resolve = finish;
  });
  return { promise, resolve };
}

function withComposerEnvironment() {
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const originalFrame = Object.getOwnPropertyDescriptor(globalThis, "requestAnimationFrame");
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      addEventListener: () => {},
      removeEventListener: () => {},
      matchMedia: () => ({ matches: true }),
    },
  });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    },
  });
  Object.defineProperty(globalThis, "requestAnimationFrame", {
    configurable: true,
    value: () => 1,
  });
  return () => {
    for (const [name, descriptor] of [
      ["window", originalWindow],
      ["localStorage", originalStorage],
      ["requestAnimationFrame", originalFrame],
    ] as const) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else Reflect.deleteProperty(globalThis, name);
    }
  };
}

test("a late send acknowledgment cannot unlock or clear another chat composer", async () => {
  const restore = withComposerEnvironment();
  const keyA = "prompta.reply-draft.v1.race-chat-A";
  const keyB = "prompta.reply-draft.v1.race-chat-B";
  const first = deferred<{ ok: boolean; message: string }>();
  const second = deferred<{ ok: boolean; message: string }>();
  rememberComposerDraft(keyA, "First message");
  rememberComposerDraft(keyB, "Second message");
  const props = (chatId: string) => ({
    mode: "reply" as const,
    chatId,
    onSend: () => (chatId === "race-chat-A" ? first.promise : second.promise),
    onNewChat: () => {},
  });
  const model = createChatComposerController(props("race-chat-A"));
  const dispose = model.mount();
  try {
    expect(model.draft.value).toBe("First message");
    const sendingA = model.submit();
    model.syncProps(props("race-chat-B"));
    expect(model.draft.value).toBe("Second message");
    const sendingB = model.submit();
    first.resolve({ ok: true, message: "" });
    await sendingA;
    expect(model.draft.value).toBe("Second message");
    expect(model.sending.value).toBe(true);
    expect(readComposerDraft(keyA)).toBeUndefined();
    second.resolve({ ok: true, message: "" });
    await sendingB;
    expect(model.sending.value).toBe(false);
    expect(model.draft.value).toBe("");
  } finally {
    dispose();
    clearComposerDraft(keyA);
    clearComposerDraft(keyB);
    restore();
  }
});

test("returning to a chat with a newer draft survives its earlier acknowledgment", async () => {
  const restore = withComposerEnvironment();
  const keyA = "prompta.reply-draft.v1.race-return-A";
  const pending = deferred<{ ok: boolean; message: string }>();
  rememberComposerDraft(keyA, "Original");
  const props = (chatId: string) => ({
    mode: "reply" as const,
    chatId,
    onSend: () => pending.promise,
    onNewChat: () => {},
  });
  const model = createChatComposerController(props("race-return-A"));
  const dispose = model.mount();
  try {
    const sending = model.submit();
    model.syncProps(props("race-return-B"));
    model.syncProps(props("race-return-A"));
    model.draft.value = "Newer draft";
    rememberComposerDraft(keyA, "Newer draft");
    pending.resolve({ ok: true, message: "" });
    await sending;
    expect(model.draft.value).toBe("Newer draft");
    expect(readComposerDraft(keyA)).toBe("Newer draft");
    expect(model.sending.value).toBe(false);
  } finally {
    dispose();
    clearComposerDraft(keyA);
    restore();
  }
});
