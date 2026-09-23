import type { Attachment } from "svelte/attachments";

type TextInput = HTMLInputElement | HTMLTextAreaElement;

export type ConversationViewportSnapshot = {
  pinnedToBottom: boolean;
  scrollTop: number;
};

const CONVERSATION_BOTTOM_SLOP = 24;

let conversationViewportElement: HTMLElement | null = null;
let conversationViewportRestoreToken = 0;

export function conversationViewport(): Attachment<HTMLElement> {
  return (element) => {
    conversationViewportElement = element;

    return () => {
      if (conversationViewportElement === element) conversationViewportElement = null;

      conversationViewportRestoreToken += 1;
    };
  };
}

export function captureConversationViewport(): ConversationViewportSnapshot {
  const element = conversationViewportElement;

  if (!element) return { pinnedToBottom: true, scrollTop: 0 };

  const maxScrollTop = Math.max(0, element.scrollHeight - element.clientHeight);
  const bottomGap = Math.max(0, maxScrollTop - element.scrollTop);

  return {
    pinnedToBottom: bottomGap <= CONVERSATION_BOTTOM_SLOP,
    scrollTop: element.scrollTop,
  };
}

export function restoreConversationViewport(
  snapshot: Partial<ConversationViewportSnapshot>,
  forceBottom = false,
) {
  const element = conversationViewportElement;

  if (!element) return;

  const restoreToken = ++conversationViewportRestoreToken;
  requestAnimationFrame(() => {
    if (
      restoreToken !== conversationViewportRestoreToken ||
      conversationViewportElement !== element
    ) {
      return;
    }

    if (forceBottom || snapshot.pinnedToBottom) {
      element.scrollTop = element.scrollHeight;

      return;
    }

    const maxScrollTop = Math.max(0, element.scrollHeight - element.clientHeight);
    const rememberedScrollTop = Math.max(0, Number(snapshot.scrollTop) || 0);
    element.scrollTop = Math.min(rememberedScrollTop, maxScrollTop);
  });
}

export function focusOnRequest(
  getRequest: () => number,
): Attachment<TextInput | HTMLButtonElement> {
  return (element) => {
    let lastRequest = 0;

    $effect(() => {
      const request = getRequest();

      if (!request || request === lastRequest) return;

      lastRequest = request;
      requestAnimationFrame(() => element.focus({ preventScroll: true }));
    });
  };
}

export function clickOnRequest(getRequest: () => number): Attachment<HTMLInputElement> {
  return (element) => {
    let lastRequest = 0;

    $effect(() => {
      const request = getRequest();

      if (!request || request === lastRequest) return;

      lastRequest = request;
      element.click();
    });
  };
}

export function blurOnRequest(getRequest: () => number): Attachment<TextInput | HTMLButtonElement> {
  return (element) => {
    let lastRequest = 0;

    $effect(() => {
      const request = getRequest();

      if (!request || request === lastRequest) return;

      lastRequest = request;
      element.blur();
    });
  };
}

export function composerTextarea(
  getValue: () => string,
  getFocusRequest: () => number,
  getSelectEndRequest: () => number,
): Attachment<HTMLTextAreaElement> {
  return (element) => {
    let lastFocusRequest = 0;
    let lastSelectEndRequest = 0;

    $effect(() => {
      const value = getValue();
      element.style.overflowY = "hidden";
      element.style.height = value ? "auto" : "34px";

      if (value) {
        const contentHeight = element.scrollHeight;
        element.style.height = String(Math.min(180, contentHeight)) + "px";
        element.style.overflowY = contentHeight > 180 ? "auto" : "hidden";
      }
    });

    $effect(() => {
      const request = getFocusRequest();

      if (!request || request === lastFocusRequest) return;

      lastFocusRequest = request;
      requestAnimationFrame(() => element.focus());
    });

    $effect(() => {
      const request = getSelectEndRequest();

      if (!request || request === lastSelectEndRequest) return;

      lastSelectEndRequest = request;
      requestAnimationFrame(() => {
        element.focus();
        const end = getValue().length;
        element.setSelectionRange(end, end);
      });
    });
  };
}

export function scrollToTopOnRequest(getRequest: () => number): Attachment<HTMLElement> {
  return (element) => {
    let lastRequest = 0;

    $effect(() => {
      const request = getRequest();

      if (!request || request === lastRequest) return;

      lastRequest = request;
      requestAnimationFrame(() => {
        element.scrollTop = 0;
      });
    });
  };
}

export function stickToBottom(getFingerprint: () => string): Attachment<HTMLElement> {
  return (element) => {
    let nearBottom = true;
    let initialized = false;

    const updateNearBottom = () => {
      nearBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 120;
    };

    element.addEventListener("scroll", updateNearBottom, { passive: true });

    $effect(() => {
      getFingerprint();
      const shouldScroll = !initialized || nearBottom;
      initialized = true;

      if (shouldScroll) {
        requestAnimationFrame(() => {
          element.scrollTop = element.scrollHeight;
          updateNearBottom();
        });
      }
    });

    return () => element.removeEventListener("scroll", updateNearBottom);
  };
}

export function clickOutside(onOutside: () => void): Attachment<HTMLElement> {
  return (element) => {
    const handlePointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !element.contains(event.target)) onOutside();
    };

    document.addEventListener("pointerdown", handlePointerDown);

    return () => document.removeEventListener("pointerdown", handlePointerDown);
  };
}

export function dialogVisibility(
  getOpen: () => boolean,
  getModal: () => boolean,
  onNativeClose: () => void,
): Attachment<HTMLDialogElement> {
  return (element) => {
    const handleClose = () => onNativeClose();
    element.addEventListener("close", handleClose);

    $effect(() => {
      const shouldOpen = getOpen();
      const modal = getModal();

      if (shouldOpen && !element.open) {
        if (modal) element.showModal();
        else element.show();
      } else if (!shouldOpen && element.open) {
        element.close();
      }
    });

    return () => element.removeEventListener("close", handleClose);
  };
}
