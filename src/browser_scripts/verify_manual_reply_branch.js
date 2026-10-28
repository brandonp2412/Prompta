(() => {
      const conversation = __CONVERSATION__;
      const parent = __PARENT__;
      if (location.origin !== "https://chatgpt.com" || location.pathname !== "/c/" + conversation) return false;
      const nodes = [...document.querySelectorAll(
        'main [data-message-author-role="assistant"][data-message-id], main [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids]'
      )].filter((node) => node.getClientRects().length > 0 && getComputedStyle(node).visibility !== "hidden");
      const last = nodes.at(-1);
      if (!last) return false;
      const legacy = last.getAttribute("data-message-id");
      const ids = legacy ? [legacy] : (last.getAttribute("data-chatgpt-search-message-ids") || "").trim().split(/\s+/);
      return ids.includes(parent);
    })()
