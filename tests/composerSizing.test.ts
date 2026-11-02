import { expect, test } from "bun:test";
import type React from "react";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createChatComposerController } from "../src/ui/ChatComposerController";

test("composer grows with an unbounded max-height and scrolls when capped", async () => {
  GlobalRegistrator.register();
  const originalStyles = Object.getOwnPropertyDescriptor(globalThis, "getComputedStyle");
  let maxHeight = "none";
  Object.defineProperty(globalThis, "getComputedStyle", {
    configurable: true,
    value: () => ({ maxHeight }),
  });
  const textarea = document.createElement("textarea");
  textarea.style.height = "20px";
  textarea.style.overflowY = "hidden";
  Object.defineProperty(textarea, "scrollHeight", { value: 120 });
  textarea.getAnimations = () => [];
  textarea.getBoundingClientRect = () => new DOMRect(0, 0, 0, 20);
  const model = createChatComposerController({
    mode: "fresh",
    onSend: async () => ({ ok: true, message: "" }),
    onNewChat: () => {},
  });
  model.textarea.value = textarea;
  try {
    model.draftChanged({
      currentTarget: { value: "Line one" },
    } as React.FormEvent<HTMLTextAreaElement>);
    expect(textarea.style.height).toBe("120px");
    expect(textarea.style.overflowY).toBe("hidden");

    maxHeight = "72px";
    model.draftChanged({
      currentTarget: { value: "Line two" },
    } as React.FormEvent<HTMLTextAreaElement>);
    expect(textarea.style.height).toBe("72px");
    expect(textarea.style.overflowY).toBe("auto");
  } finally {
    if (originalStyles) Object.defineProperty(globalThis, "getComputedStyle", originalStyles);
    else Reflect.deleteProperty(globalThis, "getComputedStyle");
    await GlobalRegistrator.unregister();
  }
});
