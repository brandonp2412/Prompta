import { describe, expect, test } from "bun:test";

import { copyText } from "./clipboard";

type FakeTextarea = {
  value: string;
  style: Record<string, string>;
  removed: boolean;
  selected: boolean;
  setAttribute: (name: string, value: string) => void;
  select: () => void;
  remove: () => void;
};

function fakeDocument(copyResult = true) {
  const textarea: FakeTextarea = {
    value: "",
    style: {},
    removed: false,
    selected: false,
    setAttribute() {},
    select() {
      this.selected = true;
    },
    remove() {
      this.removed = true;
    },
  };
  let appended: FakeTextarea | null = null;
  let command = "";
  let focused = false;

  const document = {
    activeElement: {
      focus(options?: FocusOptions) {
        focused = options?.preventScroll === true;
      },
    },
    body: {
      appendChild(node: FakeTextarea) {
        appended = node;
      },
    },
    createElement() {
      return textarea;
    },
    execCommand(nextCommand: string) {
      command = nextCommand;
      return copyResult;
    },
  } as unknown as Document;

  return {
    document,
    textarea,
    state: () => ({ appended, command, focused }),
  };
}

describe("copyText", () => {
  test("uses the Clipboard API when it succeeds", async () => {
    let copied = "";
    const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
    const documentDescriptor = Object.getOwnPropertyDescriptor(globalThis, "document");

    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: {
        clipboard: {
          async writeText(value: string) {
            copied = value;
          },
        },
      },
    });
    Object.defineProperty(globalThis, "document", {
      configurable: true,
      get() {
        throw new Error("legacy fallback should not run");
      },
    });

    try {
      expect(await copyText("hello")).toBe(true);
      expect(copied).toBe("hello");
    } finally {
      if (navigatorDescriptor) Object.defineProperty(globalThis, "navigator", navigatorDescriptor);
      else delete (globalThis as { navigator?: Navigator }).navigator;

      if (documentDescriptor) Object.defineProperty(globalThis, "document", documentDescriptor);
      else delete (globalThis as { document?: Document }).document;
    }
  });

  test("falls back when Clipboard API writes are denied and restores focus", async () => {
    const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
    const documentDescriptor = Object.getOwnPropertyDescriptor(globalThis, "document");
    const fallback = fakeDocument();

    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: {
        clipboard: {
          async writeText() {
            throw new Error("denied");
          },
        },
      },
    });
    Object.defineProperty(globalThis, "document", {
      configurable: true,
      value: fallback.document,
    });

    try {
      expect(await copyText("fallback text")).toBe(true);
      expect(fallback.textarea.value).toBe("fallback text");
      expect(fallback.textarea.selected).toBe(true);
      expect(fallback.textarea.removed).toBe(true);
      expect(fallback.state()).toEqual({
        appended: fallback.textarea,
        command: "copy",
        focused: true,
      });
    } finally {
      if (navigatorDescriptor) Object.defineProperty(globalThis, "navigator", navigatorDescriptor);
      else delete (globalThis as { navigator?: Navigator }).navigator;

      if (documentDescriptor) Object.defineProperty(globalThis, "document", documentDescriptor);
      else delete (globalThis as { document?: Document }).document;
    }
  });

  test("reports failure when neither copy mechanism succeeds", async () => {
    const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
    const documentDescriptor = Object.getOwnPropertyDescriptor(globalThis, "document");
    const fallback = fakeDocument(false);

    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: {},
    });
    Object.defineProperty(globalThis, "document", {
      configurable: true,
      value: fallback.document,
    });

    try {
      expect(await copyText("nope")).toBe(false);
      expect(fallback.textarea.removed).toBe(true);
      expect(fallback.state().command).toBe("copy");
    } finally {
      if (navigatorDescriptor) Object.defineProperty(globalThis, "navigator", navigatorDescriptor);
      else delete (globalThis as { navigator?: Navigator }).navigator;

      if (documentDescriptor) Object.defineProperty(globalThis, "document", documentDescriptor);
      else delete (globalThis as { document?: Document }).document;
    }
  });
});
