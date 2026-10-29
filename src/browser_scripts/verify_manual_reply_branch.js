(() => {
      const conversation = __CONVERSATION__;
      const parent = __PARENT__;
      if (location.origin !== "https://chatgpt.com" || location.pathname !== "/c/" + conversation) return false;
      const nodes = [...document.querySelectorAll(
        'main [data-message-author-role="assistant"][data-message-id], main [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids]'
      )].filter((node) => node.getClientRects().length > 0 && getComputedStyle(node).visibility !== "hidden");
      const last = nodes.at(-1);
      if (!last) return false;
      const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
      if (!uuid.test(parent)) return false;
      const legacy = last.getAttribute("data-message-id");
      let candidate = legacy;
      if (!candidate) {
        try {
          const raw = last.getAttribute("data-chatgpt-search-message-ids") || "";
          const ids = raw.trim().startsWith("[") ? JSON.parse(raw) : raw.trim().split(/\s+/);
          if (!Array.isArray(ids) || !ids.length ||
              !ids.every((id) => typeof id === "string" && uuid.test(id))) return false;
          if (new Set(ids.map((id) => id.toLowerCase())).size !== 1) return false;
          candidate = ids[0];
        } catch { return false; }
      }
      return typeof candidate === "string" && uuid.test(candidate) && candidate.toLowerCase() === parent.toLowerCase();
    })()
