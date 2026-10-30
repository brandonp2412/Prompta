(() => {
      const conversation = __CONVERSATION__;
      const parent = __PARENT__;
      if (location.origin !== "https://chatgpt.com" || location.pathname !== "/c/" + conversation) return false;
      const nodes = [...document.querySelectorAll(
        'main [data-message-author-role="assistant"][data-message-id], main [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids], main [data-content-search-unit-key$=":assistant"]'
      )].filter((node) => node.getClientRects().length > 0 && getComputedStyle(node).visibility !== "hidden");
      const last = nodes.at(-1);
      if (!last) return false;
      // A newer user turn means the stored parent is no longer the reply tip.
      const users = [...document.querySelectorAll(
        'main [data-message-author-role="user"], main [data-chatgpt-search-unit-key$=":user"], main [data-content-search-unit-key$=":user"]'
      )].filter((node) => node.getClientRects().length > 0 && getComputedStyle(node).visibility !== "hidden");
      const lastUser = users.at(-1);
      if (lastUser && (last.compareDocumentPosition(lastUser) & Node.DOCUMENT_POSITION_FOLLOWING)) return false;
      const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
      if (!uuid.test(parent)) return false;
      const legacy = last.getAttribute("data-message-id");
      let candidate = legacy;
      if (!candidate) {
        try {
          const raw = last.getAttribute("data-chatgpt-search-message-ids") || last.getAttribute("data-content-search-message-ids") || "";
          const ids = raw.trim().startsWith("[") ? JSON.parse(raw) : raw.trim().split(/\s+/);
          if (!Array.isArray(ids) || !ids.length ||
              !ids.every((id) => typeof id === "string" && uuid.test(id))) return false;
          // Tool and final-message IDs can share an assistant turn.
          // Only the persisted exact parent can authorize a reply.
          candidate = ids.find((id) => id.toLowerCase() === parent.toLowerCase()) || null;
        } catch { return false; }
      }
      return typeof candidate === "string" && uuid.test(candidate) && candidate.toLowerCase() === parent.toLowerCase();
    })()
