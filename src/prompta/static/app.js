const state = {
  chats: [],
  selectedId: null,
  selectedUpdatedAt: null,
  selectedFingerprint: "",
  selectedChat: null,
  search: "",
  sidebarFingerprint: "",
  refreshTimer: null,
  mode: "chats",
  logFingerprint: "",
  sending: false,
  composingNew: false,
  pendingNewId: null,
  pendingNewSend: null,
  pendingReplies: new Map(),
  newChatFingerprint: "",
  chatsRequestId: 0,
  selectedRequestId: 0,
  sidebarRefreshTimer: null,
  clientSequence: 0,
};

function syncViewportHeight() {
  const viewportHeight = window.visualViewport?.height || window.innerHeight;
  document.documentElement.style.setProperty("--app-height", `${Math.round(viewportHeight)}px`);
}

syncViewportHeight();
window.addEventListener("resize", syncViewportHeight);
window.visualViewport?.addEventListener("resize", syncViewportHeight);

const els = {
  chatList: document.querySelector("#chatList"),
  searchInput: document.querySelector("#searchInput"),
  conversation: document.querySelector("#conversation"),
  emptyState: document.querySelector("#emptyState"),
  viewport: document.querySelector("#conversationViewport"),
  chatHeading: document.querySelector("#chatHeading"),
  statusChip: document.querySelector("#statusChip"),
  syncLabel: document.querySelector("#syncLabel"),
  cacheSummary: document.querySelector("#cacheSummary"),
  globalLiveOrb: document.querySelector("#globalLiveOrb"),
  openSidebar: document.querySelector("#openSidebar"),
  closeSidebar: document.querySelector("#closeSidebar"),
  sidebarScrim: document.querySelector("#sidebarScrim"),
  logsButton: document.querySelector("#logsButton"),
  newChatButton: document.querySelector("#newChatButton"),
  logsViewport: document.querySelector("#logsViewport"),
  logOutput: document.querySelector("#logOutput"),
  logsMeta: document.querySelector("#logsMeta"),
  messageForm: document.querySelector("#messageForm"),
  messageInput: document.querySelector("#messageInput"),
  sendButton: document.querySelector("#sendButton"),
  composerStatus: document.querySelector("#composerStatus"),
};

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("./sw.js").catch((error) => {
    console.debug("Prompta service worker unavailable", error);
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatRelativeTime(epochSeconds) {
  if (!epochSeconds) return "";
  const delta = Date.now() - epochSeconds * 1000;
  const abs = Math.abs(delta);
  if (abs < 45_000) return "now";
  if (abs < 3_600_000) return `${Math.max(1, Math.round(abs / 60_000))}m`;
  if (abs < 86_400_000) return `${Math.round(abs / 3_600_000)}h`;
  if (abs < 604_800_000) return `${Math.round(abs / 86_400_000)}d`;
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" })
    .format(new Date(epochSeconds * 1000));
}

function sameLocalDay(epochSeconds, offsetDays = 0) {
  if (!epochSeconds) return false;
  const d = new Date(epochSeconds * 1000);
  const target = new Date();
  target.setDate(target.getDate() - offsetDays);
  return d.getFullYear() === target.getFullYear()
    && d.getMonth() === target.getMonth()
    && d.getDate() === target.getDate();
}

function chatTitle(chat) {
  const title = (chat.title || "").replace(/^ChatGPT\s*[-–—:]?\s*/i, "").trim();
  if (title && title.toLowerCase() !== "chatgpt") return title;
  if (chat.job_name) return chat.job_name.replaceAll("-", " ");
  const preview = (chat.preview || "").trim();
  if (preview) return preview.slice(0, 72);
  return "Untitled conversation";
}

function truncate(value, length = 88) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length <= length ? text : `${text.slice(0, length - 1)}…`;
}

function nextClientSendId() {
  state.clientSequence += 1;
  return `client-${Date.now()}-${state.clientSequence}`;
}

function pendingNewMatchesChat(chat, pending) {
  if (!pending) return false;
  if (pending.conversationId && chat.id === pending.conversationId) return true;
  const prompt = String(chat.prompt || "").trim();
  const preview = String(chat.preview || "").trim();
  const message = String(pending.message || "").trim();
  if (!message || (prompt !== message && preview !== message)) return false;
  const createdAt = Number(chat.created_at || chat.updated_at || 0);
  return Math.abs(createdAt - Number(pending.updatedAt || 0)) <= 15;
}

function sidebarChats() {
  const pending = state.pendingNewSend;
  if (!pending || state.chats.some((chat) => pendingNewMatchesChat(chat, pending))) {
    return state.chats;
  }
  if (state.search && !pending.message.toLowerCase().includes(state.search.toLowerCase())) {
    return state.chats;
  }
  return [{
    id: `__pending-new-${pending.clientId}`,
    title: "",
    job_name: "",
    preview: pending.message,
    status: "pending",
    updated_at: pending.updatedAt,
    message_count: 1,
    pending_new: true,
  }, ...state.chats];
}

function groupChats(chats) {
  const groups = [
    ["Active", chats.filter((chat) => chat.status === "active" || chat.pending_new)],
    ["Today", chats.filter((chat) => chat.status !== "active" && !chat.pending_new && sameLocalDay(chat.updated_at))],
    ["Yesterday", chats.filter((chat) => chat.status !== "active" && !chat.pending_new && sameLocalDay(chat.updated_at, 1))],
    ["Previous", chats.filter((chat) => chat.status !== "active" && !chat.pending_new
      && !sameLocalDay(chat.updated_at)
      && !sameLocalDay(chat.updated_at, 1))],
  ];
  return groups.filter(([, items]) => items.length);
}

function statusClass(status) {
  return ["active", "complete"].includes(status) ? status : "neutral";
}

function displayStatus(status) {
  if (status === "active" || status === "complete") return status;
  return "cached";
}

function renderSidebar(force = false) {
  const chats = sidebarChats();
  const fingerprint = JSON.stringify(chats.map((chat) => [
    chat.id,
    chat.status,
    chat.status === "active" ? "" : chat.updated_at,
    chat.title,
    chat.status === "active" ? "" : chat.preview,
    chat.message_count,
    chat.pending_new,
  ])) + state.selectedId + state.composingNew;

  if (!force && fingerprint === state.sidebarFingerprint) return;
  state.sidebarFingerprint = fingerprint;

  if (!chats.length) {
    els.chatList.innerHTML = `
      <div class="list-empty">
        ${state.search ? "No cached chats match your search." : "No cached conversations yet.<br>Prompta runs will appear here live."}
      </div>`;
    return;
  }

  els.chatList.innerHTML = groupChats(chats).map(([label, chats]) => `
    <section class="chat-group">
      <div class="chat-group-label">${escapeHtml(label)}</div>
      ${chats.map((chat) => `
        <button class="chat-item ${(chat.pending_new ? state.composingNew : chat.id === state.selectedId || (state.composingNew && pendingNewMatchesChat(chat, state.pendingNewSend))) ? "selected" : ""}"
                data-chat-id="${escapeHtml(chat.id)}"
                data-pending-new="${chat.pending_new ? "true" : "false"}">
          <div class="chat-item-top">
            <span class="item-status-dot ${statusClass(chat.status)}"></span>
            <span class="chat-title">${escapeHtml(chatTitle(chat))}</span>
          </div>
          <div class="chat-preview">${escapeHtml(truncate(chat.preview || "Waiting for messages…"))}</div>
          <div class="chat-meta">
            <span class="chat-job">${escapeHtml(chat.job_name || `${chat.message_count || 0} messages`)}</span>
            <span class="chat-time">${escapeHtml(formatRelativeTime(chat.updated_at))}</span>
          </div>
        </button>
      `).join("")}
    </section>
  `).join("");

  for (const item of els.chatList.querySelectorAll("[data-chat-id]")) {
    item.addEventListener("click", () => {
      if (item.dataset.pendingNew === "true") {
        renderNewChat();
        document.body.classList.remove("sidebar-open");
        return;
      }
      selectChat(item.dataset.chatId);
    });
  }
}

function inlineMarkdown(text) {
  let html = escapeHtml(text);
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noreferrer noopener">$1</a>');
  html = html.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>');
  html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  return html;
}

function renderTextBlock(text) {
  const lines = text.replace(/\r/g, "").split("\n");
  const out = [];
  let listType = null;
  let paragraph = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      out.push(`<p>${inlineMarkdown(paragraph.join("\n")).replaceAll("\n", "<br>")}</p>`);
      paragraph = [];
    }
  };
  const closeList = () => {
    if (listType) {
      out.push(`</${listType}>`);
      listType = null;
    }
  };

  for (const line of lines) {
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);

    if (heading) {
      flushParagraph();
      closeList();
      const level = heading[1].length;
      out.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    if (unordered || ordered) {
      flushParagraph();
      const nextType = unordered ? "ul" : "ol";
      if (listType !== nextType) {
        closeList();
        listType = nextType;
        out.push(`<${listType}>`);
      }
      out.push(`<li>${inlineMarkdown((unordered || ordered)[1])}</li>`);
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      closeList();
      continue;
    }

    closeList();
    paragraph.push(line);
  }

  flushParagraph();
  closeList();
  return out.join("");
}

function renderMarkdown(raw) {
  const source = String(raw || "");
  const pattern = /```([^\n`]*)\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let html = "";
  let match;

  while ((match = pattern.exec(source)) !== null) {
    html += renderTextBlock(source.slice(lastIndex, match.index));
    const language = match[1].trim() || "code";
    const code = match[2].replace(/\n$/, "");
    html += `
      <div class="code-block">
        <div class="code-header">
          <span>${escapeHtml(language)}</span>
          <button type="button" class="copy-code" data-code="${encodeURIComponent(code)}">copy</button>
        </div>
        <pre><code>${escapeHtml(code)}</code></pre>
      </div>`;
    lastIndex = pattern.lastIndex;
  }

  html += renderTextBlock(source.slice(lastIndex));
  return html || "<p></p>";
}

function renderMessageSection(message, allowStreaming = true) {
  const role = message.role === "user" ? "user" : "assistant";
  const streaming = allowStreaming && message.status === "streaming";
  const label = message.send_error ? "Send error" : "Prompta run";
  return `
    <section class="message ${role}${message.send_error ? " send-error" : ""}">
      <div class="message-inner">
        ${role === "assistant" ? `
          <div class="message-label"><span class="assistant-avatar">${message.send_error ? "!" : "P"}</span> ${label}</div>
        ` : ""}
        <div class="message-content">${renderMarkdown(message.content)}</div>
        ${streaming ? `
          <div class="streaming-indicator">
            <span class="streaming-dots" aria-label="Waiting for response"><i></i><i></i><i></i></span>
          </div>
        ` : ""}
      </div>
    </section>`;
}

function cachedReplyState(cachedMessages, messageText) {
  let userIndex = -1;
  for (let index = 0; index < cachedMessages.length; index += 1) {
    const message = cachedMessages[index];
    if (
      message.role === "user"
      && String(message.content || "").trim() === messageText.trim()
    ) {
      userIndex = index;
    }
  }
  const assistantSeen = userIndex >= 0 && cachedMessages.slice(userIndex + 1).some((message) => (
    message.role === "assistant" && String(message.content || "").trim()
  ));
  return { userSeen: userIndex >= 0, assistantSeen };
}

function pendingReplyMessages(conversationId, cachedMessages) {
  const pending = state.pendingReplies.get(conversationId) || [];
  const remaining = pending.filter((item) => {
    if (item.status !== "succeeded") return true;
    return !cachedReplyState(cachedMessages, item.message).assistantSeen;
  });
  if (remaining.length) state.pendingReplies.set(conversationId, remaining);
  else state.pendingReplies.delete(conversationId);

  return remaining.flatMap((item) => {
    const cachedState = cachedReplyState(cachedMessages, item.message);
    const messages = [];
    if (!cachedState.userSeen) {
      messages.push({
        message_key: `pending-user-${item.clientId || item.sendId}`,
        role: "user",
        content: item.message,
        status: "complete",
        updated_at: item.updatedAt,
      });
    }
    if (item.status !== "failed") {
      messages.push({
        message_key: `pending-assistant-${item.clientId || item.sendId}`,
        role: "assistant",
        content: "",
        status: "streaming",
        updated_at: item.updatedAt,
      });
    }
    if (item.status === "failed") {
      messages.push({
        message_key: `pending-error-${item.clientId || item.sendId}`,
        role: "assistant",
        content: `Send failed: ${item.error || "Unknown Prompta send error"}`,
        status: "complete",
        updated_at: item.updatedAt,
        send_error: true,
      });
    }
    return messages;
  });
}

function renderConversation(chat) {
  state.selectedChat = chat;
  const messages = Array.isArray(chat.messages) ? chat.messages : [];
  const pendingMessages = pendingReplyMessages(chat.id, messages);
  const visibleMessages = [
    ...messages,
    ...pendingMessages,
  ];
  const lastCachedMessage = [...messages].reverse().find((message) => (
    String(message.content || "").trim()
  ));
  const hasWaitingAssistant = pendingMessages.some((message) => (
    message.role === "assistant" && message.status === "streaming"
  ));
  if (
    chat.status === "active"
    && lastCachedMessage?.role === "user"
    && !hasWaitingAssistant
  ) {
    visibleMessages.push({
      message_key: `waiting-assistant-${lastCachedMessage.message_key || lastCachedMessage.id || "latest"}`,
      role: "assistant",
      content: "",
      status: "streaming",
      updated_at: chat.updated_at,
    });
  }
  const fingerprint = JSON.stringify(visibleMessages.map((message) => [
    message.message_key, message.status, message.updated_at, message.content, message.send_error,
  ]));

  const wasNearBottom = els.viewport.scrollHeight - els.viewport.scrollTop - els.viewport.clientHeight < 120;
  const isInitial = state.selectedFingerprint === "";
  if (fingerprint !== state.selectedFingerprint) {
    state.selectedFingerprint = fingerprint;
    els.conversation.innerHTML = visibleMessages
      .map((message) => renderMessageSection(
        message,
        chat.status === "active" || String(message.message_key || "").startsWith("pending-assistant-"),
      ))
      .join("");

    for (const button of els.conversation.querySelectorAll(".copy-code")) {
      button.addEventListener("click", async () => {
        const code = decodeURIComponent(button.dataset.code || "");
        try {
          await navigator.clipboard.writeText(code);
          const previous = button.textContent;
          button.textContent = "copied";
          setTimeout(() => { button.textContent = previous; }, 1000);
        } catch {
          button.textContent = "copy unavailable";
        }
      });
    }

    if (isInitial || wasNearBottom) {
      requestAnimationFrame(() => {
        els.viewport.scrollTop = els.viewport.scrollHeight;
      });
    }
  }

  const title = chatTitle(chat);
  const meta = [
    chat.job_name || "one-shot",
    `${visibleMessages.length} message${visibleMessages.length === 1 ? "" : "s"}`,
    chat.status === "active" ? "updating live" : formatRelativeTime(chat.updated_at),
  ].join(" · ");

  els.chatHeading.innerHTML = `
    <div class="heading-title">${escapeHtml(title)}</div>
    <div class="heading-meta">${escapeHtml(meta)}</div>`;
  els.statusChip.textContent = displayStatus(chat.status);
  els.statusChip.className = `status-chip ${statusClass(chat.status)}`;
  els.syncLabel.textContent = chat.status === "active" ? "syncing from SQLite" : "cached locally";

  els.emptyState.hidden = true;
  els.conversation.hidden = false;
  els.messageInput.disabled = state.sending;
  syncSendButton();
  state.composingNew = false;
  if (!state.sending) {
    const pendingForChat = state.pendingReplies.get(chat.id) || [];
    const latestPending = pendingForChat.at(-1);
    els.composerStatus.textContent = latestPending?.status === "failed"
      ? "Send failed. The error is shown in the chat."
      : "";
  }
}

function renderLogs(payload) {
  const lines = Array.isArray(payload.lines) ? payload.lines : [];
  const fingerprint = JSON.stringify([payload.updated_at, lines]);
  const wasNearBottom = els.logsViewport.scrollHeight
    - els.logsViewport.scrollTop
    - els.logsViewport.clientHeight < 120;
  const isInitial = !state.logFingerprint;

  if (fingerprint !== state.logFingerprint) {
    state.logFingerprint = fingerprint;
    els.logOutput.textContent = lines.length
      ? lines.join("\n")
      : "No Glass Prompta logs have been synced yet.";
    if (isInitial || wasNearBottom) {
      requestAnimationFrame(() => {
        els.logsViewport.scrollTop = els.logsViewport.scrollHeight;
      });
    }
  }

  els.logsMeta.textContent = payload.exists
    ? lines.length + " lines · synced " + formatRelativeTime(payload.updated_at)
    : "Waiting for synced journal";
}

async function loadLogs() {
  try {
    const payload = await fetchJson("api/logs?limit=800");
    renderLogs(payload);
  } catch (error) {
    els.logsMeta.textContent = "Logs unavailable";
    console.error(error);
  }
}

function showMode(mode) {
  state.mode = mode === "logs" ? "logs" : "chats";
  const logsMode = state.mode === "logs";
  els.viewport.hidden = logsMode;
  els.logsViewport.hidden = !logsMode;
  if (els.logsButton) {
    els.logsButton.textContent = logsMode ? "chats" : "logs";
    els.logsButton.classList.toggle("active", logsMode);
  }

  if (logsMode) {
    els.chatHeading.innerHTML =
      '<div class="heading-title">Glass Prompta logs</div>'
      + '<div class="heading-meta">journalctl · prompta.service · synced from Glass</div>';
    els.statusChip.textContent = "live";
    els.statusChip.className = "status-chip active";
    els.syncLabel.textContent = "Glass journal";
    els.messageInput.disabled = true;
    els.sendButton.disabled = true;
    els.composerStatus.textContent = "";
    loadLogs();
    return;
  }

  if (state.selectedId) {
    loadSelectedChat();
  } else if (state.composingNew) {
    renderNewChat();
  } else {
    clearConversation();
  }
}

function clearConversation() {
  state.composingNew = false;
  state.selectedId = null;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.selectedChat = null;
  els.emptyState.hidden = false;
  els.conversation.hidden = true;
  els.conversation.innerHTML = "";
  els.chatHeading.innerHTML = `
    <div class="heading-title">Prompta</div>
    <div class="heading-meta">Local conversation history</div>`;
  els.statusChip.textContent = "idle";
  els.statusChip.className = "status-chip neutral";
  els.syncLabel.textContent = "local cache";
  els.messageInput.disabled = true;
  syncSendButton();
  els.messageInput.placeholder = "Message Prompta…";
  els.composerStatus.textContent = "";
}

function renderNewChat() {
  const enteringNewChat = !state.composingNew;
  state.composingNew = true;
  state.selectedId = null;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.selectedChat = null;
  state.mode = "chats";

  const pending = state.pendingNewSend;
  const waiting = pending && !["failed", "succeeded"].includes(pending.status);
  const fingerprint = JSON.stringify([
    pending?.clientId || pending?.sendId || "",
    pending?.message || "",
    pending?.status || "",
    pending?.error || "",
    pending?.conversationId || "",
  ]);

  if (fingerprint !== state.newChatFingerprint) {
    state.newChatFingerprint = fingerprint;
    if (pending) {
      const messages = [{
        message_key: `pending-user-${pending.clientId || pending.sendId}`,
        role: "user",
        content: pending.message,
        status: "complete",
        updated_at: pending.updatedAt,
      }];
      if (pending.status === "failed") {
        messages.push({
          message_key: `pending-error-${pending.clientId || pending.sendId}`,
          role: "assistant",
          content: `Send failed: ${pending.error || "Unknown Prompta send error"}`,
          status: "complete",
          updated_at: pending.updatedAt,
          send_error: true,
        });
      } else {
        messages.push({
          message_key: `pending-assistant-${pending.clientId || pending.sendId}`,
          role: "assistant",
          content: "",
          status: "streaming",
          updated_at: pending.updatedAt,
        });
      }
      els.emptyState.hidden = true;
      els.conversation.hidden = false;
      els.conversation.innerHTML = messages.map(renderMessageSection).join("");
      requestAnimationFrame(() => {
        els.viewport.scrollTop = els.viewport.scrollHeight;
      });
    } else {
      els.emptyState.hidden = false;
      els.conversation.hidden = true;
      els.conversation.innerHTML = "";
    }

    els.chatHeading.innerHTML = `
      <div class="heading-title">New chat</div>
      <div class="heading-meta">${pending ? "Queued through the live Prompta session" : "Starts a fresh ChatGPT conversation"}</div>`;
    els.statusChip.textContent = pending?.status || "new";
    els.statusChip.className = "status-chip neutral";
    els.syncLabel.textContent = pending ? "send queued" : "fresh conversation";
    els.messageInput.disabled = Boolean(waiting);
    syncSendButton();
    els.messageInput.placeholder = "Start a new chat…";
    els.composerStatus.textContent = pending?.status === "failed"
      ? "Send failed. The error is shown in the chat."
      : "";
  }

  if (enteringNewChat) {
    els.viewport.hidden = false;
    els.logsViewport.hidden = true;
    if (els.logsButton) {
      els.logsButton.textContent = "logs";
      els.logsButton.classList.remove("active");
    }
    history.replaceState(null, "", `${location.pathname}${location.search}`);
    renderSidebar(true);
    document.body.classList.remove("sidebar-open");
    if (!waiting && matchMedia("(pointer: fine)").matches) {
      requestAnimationFrame(() => els.messageInput.focus());
    }
  }
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `${response.status} ${response.statusText}`);
  }
  return data;
}

async function loadChats({ refreshSelected = true } = {}) {
  const requestId = ++state.chatsRequestId;
  try {
    const query = state.search ? `?q=${encodeURIComponent(state.search)}` : "";
    const payload = await fetchJson(`api/chats${query}`);
    if (requestId !== state.chatsRequestId) return;
    state.chats = payload.chats || [];
    els.globalLiveOrb.classList.add("live");

    const activeCount = state.chats.filter((chat) => chat.status === "active").length;
    els.cacheSummary.textContent = `${state.chats.length} cached · ${activeCount} active`;

    const hashId = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
    if (!state.selectedId && hashId && state.chats.some((chat) => chat.id === hashId)) {
      state.selectedId = hashId;
    }
    if (!state.selectedId && state.chats.length && !state.composingNew) {
      state.selectedId = state.chats[0].id;
    }

    if (
      state.selectedId
      && !state.composingNew
      && state.pendingNewId !== state.selectedId
      && !state.chats.some((chat) => chat.id === state.selectedId)
      && !state.search
    ) {
      state.selectedId = state.chats[0]?.id || null;
      state.selectedFingerprint = "";
    }

    renderSidebar();

    if (state.mode === "chats") {
      if (state.selectedId) {
        const summary = state.chats.find((chat) => chat.id === state.selectedId);
        const shouldRefresh = !summary
          || summary.status === "active"
          || state.selectedUpdatedAt !== summary.updated_at
          || !state.selectedFingerprint;
        if (shouldRefresh && refreshSelected) await loadSelectedChat();
      } else if (!state.composingNew) {
        clearConversation();
      }
    } else {
      await loadLogs();
    }
  } catch (error) {
    if (requestId !== state.chatsRequestId) return;
    els.globalLiveOrb.classList.remove("live");
    els.cacheSummary.textContent = "Cache unavailable";
    console.error(error);
  }
}

async function loadSelectedChat() {
  if (!state.selectedId || state.mode !== "chats") return;
  const selectedId = state.selectedId;
  const requestId = ++state.selectedRequestId;
  try {
    const chat = await fetchJson("api/chats/" + encodeURIComponent(selectedId));
    if (
      requestId !== state.selectedRequestId
      || selectedId !== state.selectedId
      || chat.id !== state.selectedId
    ) return;
    if (state.pendingNewId === chat.id) {
      state.pendingNewId = null;
      if (state.pendingNewSend?.conversationId === chat.id) state.pendingNewSend = null;
    }
    state.selectedUpdatedAt = chat.updated_at;
    state.selectedChat = chat;
    renderConversation(chat);
  } catch (error) {
    if (requestId !== state.selectedRequestId || selectedId !== state.selectedId) return;
    const missing = String(error).startsWith("Error: 404");
    if (missing && state.pendingNewId !== state.selectedId) clearConversation();
    if (!missing || state.pendingNewId !== state.selectedId) console.error(error);
  }
}

async function selectChat(id) {
  if (!id) return;
  if (state.mode !== "chats") showMode("chats");
  if (id === state.selectedId) {
    document.body.classList.remove("sidebar-open");
    return;
  }
  state.composingNew = false;
  state.pendingNewId = null;
  els.messageInput.placeholder = "Message Prompta…";
  state.selectedId = id;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.selectedChat = null;
  history.replaceState(null, "", `#/${encodeURIComponent(id)}`);
  renderSidebar(true);
  await loadSelectedChat();
  document.body.classList.remove("sidebar-open");
}

let searchTimer;
els.searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.search = els.searchInput.value.trim();
    state.sidebarFingerprint = "";
    loadChats();
  }, 140);
});

document.addEventListener("keydown", (event) => {
  const typing = document.activeElement === els.searchInput
    || document.activeElement === els.messageInput;
  if (event.key === "/" && !typing) {
    event.preventDefault();
    els.searchInput.focus();
  }
  if (event.key === "Escape") {
    els.searchInput.blur();
    document.body.classList.remove("sidebar-open");
  }
});

els.openSidebar.addEventListener("click", () => document.body.classList.add("sidebar-open"));
els.closeSidebar.addEventListener("click", () => document.body.classList.remove("sidebar-open"));
els.sidebarScrim.addEventListener("click", () => document.body.classList.remove("sidebar-open"));
if (els.logsButton) {
  els.logsButton.addEventListener("click", () => {
    showMode(state.mode === "logs" ? "chats" : "logs");
  });
}
els.newChatButton.addEventListener("click", () => {
  state.pendingNewSend = null;
  state.newChatFingerprint = "";
  renderNewChat();
});

function resizeComposer() {
  els.messageInput.style.height = "auto";
  els.messageInput.style.overflowY = "hidden";
  const nextHeight = Math.min(180, els.messageInput.scrollHeight);
  els.messageInput.style.height = nextHeight + "px";
  if (els.messageInput.scrollHeight > 180) {
    els.messageInput.style.overflowY = "auto";
  }
}

function syncSendButton() {
  els.sendButton.disabled = els.messageInput.disabled
    || state.sending
    || !els.messageInput.value.trim();
}

function pendingReply(conversationId, sendId) {
  return (state.pendingReplies.get(conversationId) || [])
    .find((item) => item.sendId === sendId);
}

function updatePendingReply(conversationId, sendId, updates) {
  const item = pendingReply(conversationId, sendId);
  if (!item) return;
  const previousError = item.error || "";
  Object.assign(item, updates);
  if ((item.error || "") !== previousError) item.updatedAt = Date.now() / 1000;
}

async function watchSend(sendId, creatingNew, conversationId) {
  let statusFailures = 0;
  while (true) {
    await new Promise((resolve) => setTimeout(resolve, 400));
    let job;
    try {
      job = await fetchJson(`api/sends/${encodeURIComponent(sendId)}`);
      statusFailures = 0;
    } catch (error) {
      statusFailures += 1;
      if (statusFailures < 4) continue;
      job = {
        status: "failed",
        error: String(error).replace(/^Error:\s*/, ""),
      };
    }

    const status = job.status || "running";
    if (creatingNew) {
      if (state.pendingNewSend?.sendId !== sendId) return;
      const nextError = job.error || "";
      const nextConversationId = job.conversation_id || state.pendingNewSend.conversationId || "";
      const changed = state.pendingNewSend.status !== status
        || state.pendingNewSend.error !== nextError
        || state.pendingNewSend.conversationId !== nextConversationId;
      Object.assign(state.pendingNewSend, {
        status,
        error: nextError,
        conversationId: nextConversationId,
      });
      if (changed) state.pendingNewSend.updatedAt = Date.now() / 1000;
      if (status === "succeeded") {
        const newId = job.conversation_id;
        if (!newId) {
          state.pendingNewSend.status = "failed";
          state.pendingNewSend.error = "Prompta reported success without a conversation id";
          renderNewChat();
          return;
        }
        state.composingNew = false;
        state.selectedId = newId;
        state.pendingNewId = newId;
        history.replaceState(null, "", `#/${encodeURIComponent(newId)}`);
        els.messageInput.placeholder = "Message Prompta…";
        els.composerStatus.textContent = "";
        state.selectedUpdatedAt = null;
        await loadChats();
        await loadSelectedChat();
        return;
      }
      if (status === "failed") {
        renderNewChat();
        return;
      }
      if (changed) renderNewChat();
      continue;
    }

    updatePendingReply(conversationId, sendId, {
      status,
      error: job.error || "",
    });
    if (state.selectedId === conversationId) await loadSelectedChat();
    if (status === "succeeded") {
      els.composerStatus.textContent = "";
      await loadChats();
      return;
    }
    if (status === "failed") {
      els.composerStatus.textContent = "Send failed. The error is shown in the chat.";
      return;
    }
  }
}

async function sendSelectedMessage() {
  const message = els.messageInput.value.trim();
  const creatingNew = state.composingNew;
  const conversationId = state.selectedId;
  if (!message || (!creatingNew && !conversationId) || state.mode !== "chats" || state.sending) return;

  const pending = {
    clientId: nextClientSendId(),
    sendId: "",
    message,
    status: "queueing",
    error: "",
    conversationId: conversationId || "",
    updatedAt: Date.now() / 1000,
  };

  state.sending = true;
  els.messageInput.disabled = true;
  syncSendButton();
  els.messageInput.value = "";
  resizeComposer();
  els.composerStatus.textContent = "";

  if (creatingNew) {
    state.pendingNewSend = pending;
    state.newChatFingerprint = "";
    renderNewChat();
    renderSidebar(true);
  } else {
    const items = state.pendingReplies.get(conversationId) || [];
    items.push(pending);
    state.pendingReplies.set(conversationId, items);
    if (state.selectedChat?.id === conversationId) {
      renderConversation(state.selectedChat);
    }
  }

  try {
    const result = creatingNew
      ? await postJson("api/chats", { message })
      : await postJson(
        `api/chats/${encodeURIComponent(conversationId)}/messages`,
        { message },
      );
    if (!result.send_id) throw new Error("Prompta did not return a send id");

    pending.sendId = result.send_id;
    pending.status = result.status || "queued";
    pending.updatedAt = Date.now() / 1000;

    if (creatingNew) {
      state.newChatFingerprint = "";
      renderNewChat();
      renderSidebar(true);
    } else if (state.selectedChat?.id === conversationId) {
      renderConversation(state.selectedChat);
    }
    els.composerStatus.textContent = "";
    watchSend(result.send_id, creatingNew, conversationId);
  } catch (error) {
    pending.status = "failed";
    pending.error = String(error).replace(/^Error:\s*/, "");
    pending.updatedAt = Date.now() / 1000;
    if (creatingNew) {
      state.newChatFingerprint = "";
      renderNewChat();
      renderSidebar(true);
    } else if (state.selectedChat?.id === conversationId) {
      renderConversation(state.selectedChat);
    }
    els.composerStatus.textContent = "Send failed. The error is shown in the chat.";
    console.error(error);
  } finally {
    state.sending = false;
    if (!creatingNew && state.selectedId && state.mode === "chats") {
      els.messageInput.disabled = false;
      syncSendButton();
      if (matchMedia("(pointer: fine)").matches) els.messageInput.focus();
    } else if (creatingNew && state.pendingNewSend?.status === "failed" && state.mode === "chats") {
      els.messageInput.disabled = false;
      syncSendButton();
      if (matchMedia("(pointer: fine)").matches) els.messageInput.focus();
    }
  }
}

els.messageForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendSelectedMessage();
});

els.messageInput.addEventListener("input", () => {
  resizeComposer();
  syncSendButton();
});
els.messageInput.addEventListener("keydown", (event) => {
  const desktopKeyboard = matchMedia("(pointer: fine)").matches;
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing && desktopKeyboard) {
    event.preventDefault();
    sendSelectedMessage();
  }
});

window.addEventListener("hashchange", () => {
  const id = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
  if (id && id !== state.selectedId) selectChat(id);
});

function queueSidebarRefresh() {
  if (state.sidebarRefreshTimer || document.visibilityState === "hidden") return;
  state.sidebarRefreshTimer = setTimeout(async () => {
    state.sidebarRefreshTimer = null;
    await loadChats({ refreshSelected: false });
  }, 1500);
}

function queueLiveRefresh(event) {
  if (document.visibilityState === "hidden") return;

  let changedId = "";
  try {
    changedId = JSON.parse(event?.data || "{}").conversation_id || "";
  } catch {
    changedId = "";
  }

  if (changedId && changedId === state.selectedId && state.mode === "chats") {
    loadSelectedChat();
  }
  queueSidebarRefresh();
}

function startFallbackPolling() {
  if (state.refreshTimer) return;
  state.refreshTimer = setInterval(() => {
    if (document.visibilityState === "visible") loadChats();
  }, 5000);
}

function stopFallbackPolling() {
  if (!state.refreshTimer) return;
  clearInterval(state.refreshTimer);
  state.refreshTimer = null;
}

function startEventStream() {
  if (!("EventSource" in window)) {
    startFallbackPolling();
    return;
  }

  const events = new EventSource("api/events");
  events.addEventListener("open", () => {
    stopFallbackPolling();
    els.globalLiveOrb.classList.add("live");
  });
  events.addEventListener("refresh", queueLiveRefresh);
  events.addEventListener("error", () => {
    els.globalLiveOrb.classList.remove("live");
    startFallbackPolling();
  });
  window.addEventListener("pagehide", () => events.close(), { once: true });
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") loadChats();
});

resizeComposer();
registerServiceWorker();
loadChats().finally(startEventStream);
