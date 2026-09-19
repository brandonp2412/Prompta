const state = {
  chats: [],
  selectedId: null,
  selectedUpdatedAt: null,
  selectedFingerprint: "",
  search: "",
  sidebarFingerprint: "",
  refreshTimer: null,
  mode: "chats",
  logFingerprint: "",
  sending: false,
  composingNew: false,
  pendingNewId: null,
};

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

function groupChats(chats) {
  const groups = [
    ["Active", chats.filter((chat) => chat.status === "active")],
    ["Today", chats.filter((chat) => chat.status !== "active" && sameLocalDay(chat.updated_at))],
    ["Yesterday", chats.filter((chat) => chat.status !== "active" && sameLocalDay(chat.updated_at, 1))],
    ["Previous", chats.filter((chat) => chat.status !== "active"
      && !sameLocalDay(chat.updated_at)
      && !sameLocalDay(chat.updated_at, 1))],
  ];
  return groups.filter(([, items]) => items.length);
}

function statusClass(status) {
  return ["active", "complete", "interrupted"].includes(status) ? status : "neutral";
}

function renderSidebar(force = false) {
  const fingerprint = JSON.stringify(state.chats.map((chat) => [
    chat.id, chat.status, chat.updated_at, chat.title, chat.preview, chat.message_count,
  ])) + state.selectedId;

  if (!force && fingerprint === state.sidebarFingerprint) return;
  state.sidebarFingerprint = fingerprint;

  if (!state.chats.length) {
    els.chatList.innerHTML = `
      <div class="list-empty">
        ${state.search ? "No cached chats match your search." : "No cached conversations yet.<br>Prompta runs will appear here live."}
      </div>`;
    return;
  }

  els.chatList.innerHTML = groupChats(state.chats).map(([label, chats]) => `
    <section class="chat-group">
      <div class="chat-group-label">${escapeHtml(label)}</div>
      ${chats.map((chat) => `
        <button class="chat-item ${chat.id === state.selectedId ? "selected" : ""}"
                data-chat-id="${escapeHtml(chat.id)}">
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
    item.addEventListener("click", () => selectChat(item.dataset.chatId));
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

function renderConversation(chat) {
  const messages = Array.isArray(chat.messages) ? chat.messages : [];
  const fingerprint = JSON.stringify(messages.map((message) => [
    message.message_key, message.status, message.updated_at, message.content,
  ]));

  const wasNearBottom = els.viewport.scrollHeight - els.viewport.scrollTop - els.viewport.clientHeight < 120;
  const isInitial = state.selectedFingerprint === "";
  if (fingerprint !== state.selectedFingerprint) {
    state.selectedFingerprint = fingerprint;
    els.conversation.innerHTML = messages.map((message) => {
      const role = message.role === "user" ? "user" : "assistant";
      const streaming = message.status === "streaming";
      return `
        <section class="message ${role}">
          <div class="message-inner">
            ${role === "assistant" ? `
              <div class="message-label"><span class="assistant-avatar">P</span> Prompta run</div>
            ` : ""}
            <div class="message-content">${renderMarkdown(message.content)}</div>
            ${streaming ? `
              <div class="streaming-indicator">
                <span class="streaming-dots"><i></i><i></i><i></i></span>
                writing
              </div>
            ` : ""}
          </div>
        </section>`;
    }).join("");

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
    `${messages.length} message${messages.length === 1 ? "" : "s"}`,
    chat.status === "active" ? "updating live" : formatRelativeTime(chat.updated_at),
  ].join(" · ");

  els.chatHeading.innerHTML = `
    <div class="heading-title">${escapeHtml(title)}</div>
    <div class="heading-meta">${escapeHtml(meta)}</div>`;
  els.statusChip.textContent = chat.status || "cached";
  els.statusChip.className = `status-chip ${statusClass(chat.status)}`;
  els.syncLabel.textContent = chat.status === "active" ? "syncing from SQLite" : "cached locally";

  els.emptyState.hidden = true;
  els.conversation.hidden = false;
  els.messageInput.disabled = state.sending;
  els.sendButton.disabled = state.sending;
  state.composingNew = false;
  if (!state.sending) {
    els.composerStatus.textContent = chat.status === "active"
      ? "Uses the existing live ChatGPT tab."
      : "Sending will reopen this chat once if its retained tab has expired.";
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
    els.composerStatus.textContent = "Switch back to chats to send a message.";
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
  els.sendButton.disabled = true;
  els.messageInput.placeholder = "Message Prompta…";
  els.composerStatus.textContent = "Select a chat to send a message.";
}

function renderNewChat() {
  state.composingNew = true;
  state.selectedId = null;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.mode = "chats";
  els.viewport.hidden = false;
  els.logsViewport.hidden = true;
  if (els.logsButton) {
    els.logsButton.textContent = "logs";
    els.logsButton.classList.remove("active");
  }
  els.emptyState.hidden = false;
  els.conversation.hidden = true;
  els.conversation.innerHTML = "";
  els.chatHeading.innerHTML = `
    <div class="heading-title">New chat</div>
    <div class="heading-meta">Starts a fresh ChatGPT conversation</div>`;
  els.statusChip.textContent = "new";
  els.statusChip.className = "status-chip neutral";
  els.syncLabel.textContent = "fresh conversation";
  els.messageInput.disabled = false;
  els.sendButton.disabled = false;
  els.messageInput.placeholder = "Start a new chat…";
  els.composerStatus.textContent = "Your first message will open a fresh ChatGPT chat.";
  history.replaceState(null, "", `${location.pathname}${location.search}`);
  renderSidebar(true);
  document.body.classList.remove("sidebar-open");
  requestAnimationFrame(() => els.messageInput.focus());
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

async function loadChats() {
  try {
    const query = state.search ? `?q=${encodeURIComponent(state.search)}` : "";
    const payload = await fetchJson(`api/chats${query}`);
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
        if (shouldRefresh) await loadSelectedChat();
      } else if (!state.composingNew) {
        clearConversation();
      }
    } else {
      await loadLogs();
    }
  } catch (error) {
    els.globalLiveOrb.classList.remove("live");
    els.cacheSummary.textContent = "Cache unavailable";
    console.error(error);
  }
}

async function loadSelectedChat() {
  if (!state.selectedId || state.mode !== "chats") return;
  try {
    const chat = await fetchJson(`api/chats/${encodeURIComponent(state.selectedId)}`);
    if (chat.id !== state.selectedId) return;
    if (state.pendingNewId === chat.id) state.pendingNewId = null;
    state.selectedUpdatedAt = chat.updated_at;
    renderConversation(chat);
  } catch (error) {
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
els.newChatButton.addEventListener("click", renderNewChat);

function resizeComposer() {
  els.messageInput.style.height = "auto";
  els.messageInput.style.height = `${Math.min(180, els.messageInput.scrollHeight)}px`;
}

async function sendSelectedMessage() {
  const message = els.messageInput.value.trim();
  const creatingNew = state.composingNew;
  if (!message || (!creatingNew && !state.selectedId) || state.mode !== "chats" || state.sending) return;

  state.sending = true;
  els.messageInput.disabled = true;
  els.sendButton.disabled = true;
  els.composerStatus.textContent = creatingNew
    ? "Starting a fresh ChatGPT conversation…"
    : "Sending through the existing Prompta browser session…";
  try {
    const result = creatingNew
      ? await postJson("api/chats", { message })
      : await postJson(
        `api/chats/${encodeURIComponent(state.selectedId)}/messages`,
        { message },
      );
    if (creatingNew) {
      state.composingNew = false;
      state.selectedId = result.conversation_id;
      state.pendingNewId = result.conversation_id;
      history.replaceState(null, "", `#/${encodeURIComponent(result.conversation_id)}`);
      els.messageInput.placeholder = "Message Prompta…";
    }
    els.messageInput.value = "";
    resizeComposer();
    els.composerStatus.textContent = "Sent. Waiting for the cached response…";
    state.selectedUpdatedAt = null;
    await loadSelectedChat();
  } catch (error) {
    els.composerStatus.textContent = String(error).replace(/^Error:\s*/, "");
    console.error(error);
  } finally {
    state.sending = false;
    if ((state.selectedId || state.composingNew) && state.mode === "chats") {
      els.messageInput.disabled = false;
      els.sendButton.disabled = false;
      els.messageInput.focus();
    }
  }
}

els.messageForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendSelectedMessage();
});

els.messageInput.addEventListener("input", resizeComposer);
els.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    sendSelectedMessage();
  }
});

window.addEventListener("hashchange", () => {
  const id = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
  if (id && id !== state.selectedId) selectChat(id);
});

loadChats();
state.refreshTimer = setInterval(loadChats, 1000);
