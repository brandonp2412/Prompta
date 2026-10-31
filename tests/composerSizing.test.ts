import { expect, test } from "bun:test";
import type React from "react";
import { createChatComposerController } from "../src/ui/ChatComposerController";

test("composer grows with an unbounded max-height and scrolls when capped", () => {
  const originalStyles = Object.getOwnPropertyDescriptor(globalThis, "getComputedStyle");
  let maxHeight = "none";
  Object.defineProperty(globalThis, "getComputedStyle", {
    configurable: true,
    value: () => ({ maxHeight }),
  });
  const style = { height: "20px", overflowY: "hidden" };
  const model = createChatComposerController({
    mode: "fresh",
    onSend: async () => ({ ok: true, message: "" }),
    onNewChat: () => {},
  });
  model.textarea.value = {
    getAnimations: () => [],
    getBoundingClientRect: () => ({ height: 20 }),
    scrollHeight: 120,
    style,
  } as HTMLTextAreaElement;
  try {
    model.draftChanged({
      currentTarget: { value: "Line one" },
    } as React.FormEvent<HTMLTextAreaElement>);
    expect(style.height).toBe("120px");
    expect(style.overflowY).toBe("hidden");

    maxHeight = "72px";
    model.draftChanged({
      currentTarget: { value: "Line two" },
    } as React.FormEvent<HTMLTextAreaElement>);
    expect(style.height).toBe("72px");
    expect(style.overflowY).toBe("auto");
  } finally {
    if (originalStyles) Object.defineProperty(globalThis, "getComputedStyle", originalStyles);
    else Reflect.deleteProperty(globalThis, "getComputedStyle");
  }
});
