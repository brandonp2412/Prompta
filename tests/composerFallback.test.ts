import { expect, test } from "bun:test";
import { createChatComposerController } from "../src/ui/ChatComposerController";

test("explicit new-chat fallback remains usable when exact-branch sending is paused", async () => {
  const originalFrame = Object.getOwnPropertyDescriptor(globalThis, "requestAnimationFrame");
  Object.defineProperty(globalThis, "requestAnimationFrame", {
    configurable: true,
    value: () => 1,
  });
  const submitted: string[] = [];
  const props = {
    mode: "reply" as const,
    chatId: "blocked-branch",
    onSend: async () => ({
      ok: false,
      message: "Exact branch recovery is paused.",
      fallbackAvailable: true,
    }),
    onFallbackSend: async (text: string) => {
      submitted.push(text);
      return { ok: true, message: "New chat queued." };
    },
    onNewChat: () => {},
    sendDisabled: false,
  };
  const model = createChatComposerController(props);
  try {
    model.draft.value = "Continue with this answer";
    await model.submit();
    expect(model.fallbackAvailable.value).toBe(true);

    model.syncProps({ ...props, sendDisabled: true });
    expect(model.canSend.value).toBe(false);
    expect(model.canFallback.value).toBe(true);
    await model.submit(true);
    expect(submitted).toEqual(["Continue with this answer"]);
    expect(model.draft.value).toBe("");
    expect(model.feedback.value).toBe("New chat queued.");
  } finally {
    if (originalFrame) Object.defineProperty(globalThis, "requestAnimationFrame", originalFrame);
    else Reflect.deleteProperty(globalThis, "requestAnimationFrame");
  }
});

test("a globally disabled composer cannot dispatch the fallback", async () => {
  let sent = false;
  const props = {
    mode: "reply" as const,
    chatId: "disabled-branch",
    onSend: async () => ({
      ok: false,
      message: "Exact branch unavailable",
      fallbackAvailable: true,
    }),
    onFallbackSend: async () => {
      sent = true;
      return { ok: true, message: "" };
    },
    onNewChat: () => {},
    disabled: false,
  };
  const model = createChatComposerController(props);
  model.draft.value = "Keep this draft";
  await model.submit();
  model.syncProps({ ...props, disabled: true });
  expect(model.canFallback.value).toBe(false);
  await model.submit(true);
  expect(sent).toBe(false);
  expect(model.draft.value).toBe("Keep this draft");
});

test("a fallback receipt from a previous reply cannot submit in fresh-chat mode", async () => {
  let sent = false;
  const props = {
    mode: "reply" as const,
    chatId: "previous-chat",
    onSend: async () => ({
      ok: false,
      message: "The exact branch could not be recovered.",
      fallbackAvailable: true,
    }),
    onFallbackSend: async () => {
      sent = true;
      return { ok: true, message: "" };
    },
    onNewChat: () => {},
  };
  const model = createChatComposerController(props);
  model.draft.value = "Preserved text";
  await model.submit();
  expect(model.canFallback.value).toBe(true);
  model.syncProps({ ...props, mode: "fresh" as const, chatId: undefined });
  expect(model.canFallback.value).toBe(false);
  await model.submit(true);
  expect(sent).toBe(false);
});
