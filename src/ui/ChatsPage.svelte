<script lang="ts">
  import { onMount, tick, untrack } from "svelte";
  import JobsPage from "./JobsPage.svelte";
  import ChatComposer from "./ChatComposer.svelte";
  import ResultMarkdown from "./ResultMarkdown.svelte";
  import { subscribeLiveUpdates } from "./liveUpdates";
  import {
    formatStoredResponse, groupRuns, nzTime, statusLabel, turnStatus,
    type LocalTurn, type ResultStatus, type RunDetail, type RunSummary,
  } from "./resultFormatting";

  let { view, selectedRunId, newChatOpen, onSelect, onNavigate, onNewChat, onQueued }: {
    view: "jobs" | "chats";
     selectedRunId: string | null;
    newChatOpen: boolean;
    onSelect: (sendId: string | null) => void;
    onNavigate: (view: "jobs" | "chats") => void;
    onNewChat: () => void;
    onQueued: (sendId: string) => void;
  } = $props();

  const pageSize = 20;
  const preferencesKey = "prompta.local-sidebar.v1";
  const statuses: { value: ResultStatus | ""; label: string }[] = [
    { value: "", label: "All states" },
    { value: "accepted", label: "Accepted" },
    { value: "generating", label: "Generating" },
    { value: "completed", label: "Completed" },
    { value: "interrupted", label: "Interrupted" },
    { value: "unavailable", label: "Unavailable" },
    { value: "queued", label: "Queued" },
  ];

  let items = $state<RunSummary[]>([]);
  let pinnedItems = $state<RunSummary[]>([]);
  let pinnedIds = $state<string[]>([]);
  let readAt = $state<Record<string, number>>({});
  let baselineAt = $state(0);
  let drawerOpen = $state(false);
  let filtersOpen = $state(false);
  let expandedPrompts = $state<Record<string, boolean>>({});
  let total = $state(0);
  let page = $state(0);
  let search = $state("");
  let statusFilter = $state<ResultStatus | "">("");
  let detail = $state<RunDetail | null>(null);
  let turns = $state<LocalTurn[]>([]);
  let turnsError = $state("");
  let recoveringReply = $state(false);
  let copyState = $state("");
  let scrollPane = $state<HTMLDivElement>();
  let loadingList = $state(true);
  let loadingDetail = $state(false);
  let listError = $state("");
  let detailError = $state("");
  let listGeneration = 0;
  let pinsGeneration = 0;
  let detailGeneration = 0;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  let liveRefreshTimer: ReturnType<typeof setTimeout> | undefined;

  const activity = (item: RunSummary) => item.updated_at || item.created_at;
  const newestFirst = (a: RunSummary, b: RunSummary) =>
    activity(b) - activity(a) || b.created_at - a.created_at || a.send_id.localeCompare(b.send_id);
  let pinned = $derived.by(() => {
    // Pinned runs remain available when they fall outside the current local page.
    const byId = new Map([...pinnedItems, ...items].map((item) => [item.send_id, item]));
    const filtered = search.trim() || statusFilter;
    return pinnedIds
      .map((id) => byId.get(id))
      .filter((item): item is RunSummary => !!item)
      .filter((item) => !filtered || items.some((listed) => listed.send_id === item.send_id))
      .sort(newestFirst);
  });
  let groups = $derived(groupRuns(items.filter((item) => !pinnedIds.includes(item.send_id)).sort(newestFirst)));
  let pageCount = $derived(Math.min(5001, Math.max(1, Math.ceil(total / pageSize))));

  function loadPreferences() {
    try {
      const saved = localStorage.getItem(preferencesKey);
      if (saved) {
        const prefs: { baselineAt?: number; pinnedIds?: string[]; readAt?: Record<string, number> } = JSON.parse(saved);
        baselineAt = Number.isFinite(prefs.baselineAt) ? Number(prefs.baselineAt) : Date.now() / 1000;
        pinnedIds = Array.isArray(prefs.pinnedIds) ? prefs.pinnedIds.filter((id) => typeof id === "string").slice(0, 24) : [];
        readAt = prefs.readAt && typeof prefs.readAt === "object" ? prefs.readAt : {};
      } else baselineAt = Date.now() / 1000;
    } catch {
      baselineAt = Date.now() / 1000;
    }
    savePreferences();
  }

  function savePreferences() {
    try {
      // Only opaque local send IDs and timestamps are stored, never chat content.
      const recent = Object.entries(readAt).sort((a, b) => b[1] - a[1]).slice(0, 2000);
      localStorage.setItem(preferencesKey, JSON.stringify({
        baselineAt, pinnedIds, readAt: Object.fromEntries(recent),
      }));
    } catch {
      // Private browsing and disabled storage still allow in-memory navigation.
    }
  }

  function isUnread(item: RunSummary) {
    return activity(item) > (readAt[item.send_id] ?? baselineAt);
  }

  function markRead(item: RunSummary) {
    readAt = { ...readAt, [item.send_id]: Math.max(Date.now() / 1000, activity(item)) };
    savePreferences();
  }

  async function loadPins() {
    const generation = ++pinsGeneration;
    const loaded = await Promise.all(pinnedIds.map(async (id): Promise<RunSummary | null> => {
      try {
        const response = await fetch("./api/results/" + encodeURIComponent(id), { cache: "no-store" });
        if (!response.ok) return null;
        return await response.json() as RunDetail;
      } catch {
        return null;
      }
    }));
    if (generation === pinsGeneration) pinnedItems = loaded.filter((item): item is RunSummary => item !== null);
  }

  function togglePin(item: RunSummary) {
    if (pinnedIds.includes(item.send_id)) {
      pinnedIds = pinnedIds.filter((id) => id !== item.send_id);
      pinnedItems = pinnedItems.filter((pinnedItem) => pinnedItem.send_id !== item.send_id);
    } else {
      pinnedIds = [item.send_id, ...pinnedIds].slice(0, 24);
      pinnedItems = [item, ...pinnedItems];
    }
    savePreferences();
  }

  async function loadList() {
    const generation = ++listGeneration;
    loadingList = items.length === 0;
    const params = new URLSearchParams({ limit: String(pageSize), offset: String(page * pageSize) });
    if (search.trim()) params.set("q", search.trim());
    if (statusFilter) params.set("status", statusFilter);
    try {
      const response = await fetch("./api/results?" + params, { cache: "no-store" });
      if (!response.ok) throw new Error("Results could not be loaded");
      const body: { items: RunSummary[]; total: number } = await response.json();
      if (generation !== listGeneration) return;
      items = body.items;
      total = body.total;
      listError = "";
    } catch {
      if (generation === listGeneration) listError = "Local results are temporarily unavailable.";
    } finally {
      if (generation === listGeneration) loadingList = false;
    }
  }

  async function loadDetail(id: string) {
    const generation = ++detailGeneration;
    const newSelection = detail?.send_id !== id;
    if (newSelection) { detail = null; turns = []; }
    const followTail = newSelection || !!scrollPane &&
      scrollPane.scrollHeight - scrollPane.scrollTop - scrollPane.clientHeight < 96;
    loadingDetail = true;
    try {
      const path = "./api/results/" + encodeURIComponent(id);
      const [response, replyResponse] = await Promise.all([
        fetch(path, { cache: "no-store" }),
        fetch(path + "/turns", { cache: "no-store" }),
      ]);
      if (!response.ok) throw new Error("Result not found");
      const body: RunDetail = await response.json();
      const saved = replyResponse.ok ? await replyResponse.json() as { turns: LocalTurn[] } : null;
      if (generation !== detailGeneration) return;
      detail = body;
      turns = saved?.turns?.length ? saved.turns : [{
        reply_id: "", user_text: body.user_text, assistant_text: body.assistant_text,
        status: body.status, created_at: body.created_at, updated_at: body.updated_at,
      }];
      turnsError = !replyResponse.ok ? "Saved replies are temporarily unavailable locally." : "";
      detailError = "";
      if (view === "chats" && selectedRunId === id) markRead(body);
      await tick();
      if (followTail && scrollPane && selectedRunId === id) scrollPane.scrollTop = scrollPane.scrollHeight;
    } catch {
      if (generation === detailGeneration) detailError = "This run is unavailable locally.";
    } finally {
      if (generation === detailGeneration) loadingDetail = false;
    }
  }

  async function sendFresh(text: string, images: string[]) {
    const requestId = crypto.randomUUID().replaceAll("-", "");
    try {
      const response = await fetch("./api/chats", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ request_id: requestId, prompt: text, images }),
      });
      if (!response.ok) {
        return {
          ok: false, ambiguous: response.status >= 500,
          message: response.status >= 500
            ? "The queue result is uncertain. Check local Chats; no automatic resend."
            : "The fresh chat was rejected. Review the prompt or images.",
        };
      }
      const body = await response.json() as { send_id?: string };
      if (!body.send_id) throw new Error("Missing queue receipt");
      // The queue has already persisted this run locally. Show it as soon as
      // the receipt is confirmed, even if the previous list was filtered.
      page = 0;
      search = "";
      statusFilter = "";
      onQueued(body.send_id);
      void loadList();
      return { ok: true, message: "" };
    } catch {
      return {
        ok: false, ambiguous: true,
        message: "Queue confirmation was lost. Check local Chats before another explicit send; no automatic retry.",
      };
    }
  }

  async function recoverReply() {
    const id = selectedRunId;
    const original = turns.length === 1 ? turns[0] : null;
    if (!id || original?.status !== "completed" || !original.conversation_id ||
        original.message_id || recoveringReply) return;
    recoveringReply = true;
    turnsError = "";
    try {
      const response = await fetch(
        "./api/results/" + encodeURIComponent(id) + "/reply-recover",
        { method: "POST", headers: { "content-type": "application/json" }, body: "{}" },
      );
      if (!response.ok) {
        turnsError = "The original reply branch could not be verified.";
        return;
      }
      await loadDetail(id);
    } catch {
      turnsError = "Reply verification could not be completed.";
    } finally {
      recoveringReply = false;
    }
  }

  async function sendReply(text: string, _images: string[]) {
    const latest = turns.at(-1);
    if (!selectedRunId || latest?.status !== "completed"
        || !latest.conversation_id || !latest.message_id) {
      return { ok: false, message: "This saved branch is not eligible for a reply." };
    }
    return sendExactReply(selectedRunId, {
      reply_id: crypto.randomUUID().replaceAll("-", ""),
      conversation_id: latest.conversation_id,
      parent_id: latest.message_id,
      text,
    });
  }

  async function sendExactReply(sendId: string, payload: {
    reply_id: string; conversation_id: string; parent_id: string; text: string;
  }) {
    try {
      const response = await fetch("./api/results/" + encodeURIComponent(sendId) + "/reply-send", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) return {
        ok: false, ambiguous: response.status >= 500,
        message: response.status >= 500
          ? "Reply outcome could not be confirmed. Check local turns; do not resubmit blindly."
          : "Reply was not queued. Check the account-wide send gap and saved branch.",
      };
      void loadDetail(sendId);
      return { ok: true, message: "Reply intent saved; explicit dispatch is starting." };
    } catch {
      return {
        ok: false, ambiguous: true,
        message: "Reply acknowledgment was lost. Check local turns; no automatic retry.",
      };
    }
  }

  async function sendPreparedReply(turn: LocalTurn) {
    if (!selectedRunId || !turn.reply_id || !turn.conversation_id || !turn.parent_id) return;
    const result = await sendExactReply(selectedRunId, {
      reply_id: turn.reply_id,
      conversation_id: turn.conversation_id,
      parent_id: turn.parent_id,
      text: turn.user_text,
    });
    if (!result.ok) turnsError = result.message;
  }

  async function copyText(value: string, key: string) {
    try {
      await navigator.clipboard.writeText(value);
      copyState = key;
    } catch {
      copyState = "error:" + key;
    }
  }

  function refresh() {
    void loadList();
    void loadPins();
    if (view === "chats" && selectedRunId) void loadDetail(selectedRunId);
  }

  function applyFilter() {
    page = 0;
    void loadList();
  }

  function searchChanged() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(applyFilter, 300);
  }

  function movePage(next: number) {
    page = Math.max(0, Math.min(pageCount - 1, next));
    void loadList();
  }

  function selectRun(item: RunSummary) {
    markRead(item);
    drawerOpen = false;
    onSelect(item.send_id);
  }

  function showJobs() {
    drawerOpen = false;
    onNavigate("jobs");
  }

  function showChats() {
    drawerOpen = false;
    onSelect(null);
  }

  function createChat() {
    drawerOpen = false;
    onNewChat();
  }

  function escapeDrawer(event: KeyboardEvent) {
    if (event.key === "Escape" && drawerOpen) drawerOpen = false;
  }

  async function togglePrompt(key: string, event: MouseEvent) {
    const bubble = (event.currentTarget as HTMLElement).closest(".prompt-bubble");
    const originalTop = bubble?.getBoundingClientRect().top;
    expandedPrompts = { ...expandedPrompts, [key]: !expandedPrompts[key] };
    await tick();
    // Keep the start of the bubble in place instead of letting scroll anchoring grow it upward.
    if (bubble && scrollPane && originalTop !== undefined) {
      scrollPane.scrollTop += bubble.getBoundingClientRect().top - originalTop;
    }
  }

  $effect(() => {
    const id = view === "chats" ? selectedRunId : null;
    untrack(() => {
      if (id) void loadDetail(id);
      else {
        detailGeneration += 1;
        detail = null;
        turns = [];
        turnsError = "";
        detailError = "";
      }
    });
  });

  onMount(() => {
    loadPreferences();
    void loadList();
    void loadPins();
    const unsubscribe = subscribeLiveUpdates("chats", () => {
      clearTimeout(liveRefreshTimer);
      liveRefreshTimer = setTimeout(refresh, 100);
    });
    return () => {
      unsubscribe();
      clearTimeout(liveRefreshTimer);
      clearTimeout(searchTimer);
    };
  });
</script>

<svelte:window onkeydown={escapeDrawer} />

{#snippet chatItem(item: RunSummary)}
  <div class:chosen={view === "chats" && selectedRunId === item.send_id} class:unread={isUnread(item)} class="chat-entry">
    <button
      type="button"
      class="chat-row"
      onclick={() => selectRun(item)}
      aria-current={view === "chats" && selectedRunId === item.send_id ? "true" : undefined}
    >
      <span class="chat-row-top">
        {#if isUnread(item)}<span class="unread-indicator" title="Unread activity"><span class="sr-only">Unread</span></span>{/if}
        <strong>{item.title || "Untitled run"}</strong>
        <span class={"result-dot status-" + item.status} title={statusLabel(item.status)}><span class="sr-only">{statusLabel(item.status)}</span></span>
      </span>
    </button>
    <button
      type="button" class:active={pinnedIds.includes(item.send_id)} class="chat-pin"
      title={pinnedIds.includes(item.send_id) ? "Unpin local chat" : "Pin local chat"}
      aria-label={pinnedIds.includes(item.send_id) ? "Unpin " + item.title : "Pin " + item.title}
      aria-pressed={pinnedIds.includes(item.send_id)}
      onclick={() => togglePin(item)}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6ZM12 14v7" /></svg>
    </button>
  </div>
{/snippet}

<section class:drawer-open={drawerOpen} class:show-list={view === "chats" && !selectedRunId && !newChatOpen} class="chats-layout" aria-label="Prompta local chats and jobs">
  {#if drawerOpen}
    <button type="button" class="drawer-backdrop" aria-label="Close chat sidebar" onclick={() => drawerOpen = false}></button>
  {/if}
  <aside class="chats-sidebar" aria-label="Local chat sidebar">
    <div class="sidebar-brand">
      <div><strong>Prompta</strong></div>
      <button class="sidebar-close" type="button" aria-label="Close sidebar" onclick={() => drawerOpen = false}>×</button>
    </div>
    <nav class="sidebar-actions" aria-label="Main navigation">
      <button class="sidebar-primary" type="button" onclick={createChat}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7M16 4l4 4M9 15l3.5-.7L21 5.8a2.1 2.1 0 0 0-3-3l-8.5 8.5L9 15Z" /></svg>
        New chat
      </button>
      <button class:active={filtersOpen} class="sidebar-search" type="button" aria-expanded={filtersOpen} aria-controls="chat-filters" onclick={() => filtersOpen = !filtersOpen}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg>
        Search chats
        {#if search || statusFilter}<span class="filter-active-dot" aria-label="Filters active"></span>{/if}
      </button>
    </nav>
    <div class="chats-heading">
      <h2><button class="chats-heading-link" type="button" onclick={showChats}>Chats</button> <span class="chats-count">{total}</span></h2>
      <button class="chats-refresh" type="button" onclick={refresh} aria-label="Refresh local results" title="Refresh local results">↻</button>
    </div>
    {#if filtersOpen}
    <div id="chat-filters" class="chats-controls">
      <label class="search-label">
        <span class="sr-only">Search job results</span>
        <input type="search" placeholder="Search chats" bind:value={search} oninput={searchChanged} />
      </label>
      <label>
        <span class="sr-only">Filter results by state</span>
        <select bind:value={statusFilter} onchange={applyFilter}>
          {#each statuses as choice}<option value={choice.value}>{choice.label}</option>{/each}
        </select>
      </label>
    </div>
    {/if}
    {#if listError}<div class="result-error" role="alert">{listError}</div>{/if}
    <div class="chats-list">
      {#if pinned.length}
        <div class="chats-date">Pinned</div>
        {#each pinned as item (item.send_id)}{@render chatItem(item)}{/each}
      {/if}
      {#if loadingList && !items.length}
        <p class="chats-empty">Loading chats…</p>
      {:else if !items.length && !pinned.length}
        <p class="chats-empty">{search || statusFilter ? "No matching chats" : "No chats"}</p>
      {:else}
        {#each groups as group (group.date)}
          <div class="chats-date">{group.date}</div>
          {#each group.items as item (item.send_id)}{@render chatItem(item)}{/each}
        {/each}
      {/if}
    </div>
    {#if total > pageSize}
      <div class="chats-pagination">
        <span>{page + 1} / {pageCount}</span>
        <div><button disabled={page === 0} aria-label="Previous chat page" onclick={() => movePage(page - 1)}>‹</button><button disabled={page + 1 >= pageCount} aria-label="Next chat page" onclick={() => movePage(page + 1)}>›</button></div>
      </div>
    {/if}
    <div class="sidebar-footer">
      <button class:active={view === "jobs"} type="button" onclick={showJobs}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M8 9h8M8 13h8M8 17h5" /></svg>
        Jobs
      </button>
    </div>
  </aside>

  <div class="chats-detail">
    <div class="workspace-header">
      <button class="sidebar-menu" type="button" aria-label="Open chat sidebar" aria-expanded={drawerOpen} onclick={() => drawerOpen = true}>☰</button>
      <strong>{view === "jobs" ? "Jobs" : (detail?.title || detail?.job_name || "Chats")}</strong>
    </div>
    {#if view === "jobs"}
      <div class="jobs-workspace"><JobsPage /></div>
    {:else if !selectedRunId && newChatOpen}
      <div class="new-chat-empty" aria-hidden="true"></div>
      <ChatComposer mode="fresh" onSend={sendFresh} />
    {:else if !selectedRunId}
      <div class="chats-detail-empty"><button class="sidebar-primary" onclick={createChat}>New chat</button></div>
    {:else}
      <div class="chat-detail-toolbar">
        <button class="chat-detail-back" onclick={() => onSelect(null)}>‹ <span>All chats</span></button>
        {#if detail}<span class={"result-pill status-" + (turns.at(-1)?.status || detail.status)}>{turns.length > 1 ? "Latest reply · " + turnStatus(turns.at(-1)?.status || detail.status) : statusLabel(detail.status)}</span>{/if}
      </div>
      <div class="chat-transcript-scroll" bind:this={scrollPane}>
      {#if detailError}<div class="result-error" role="alert">{detailError}</div>{/if}
      {#if loadingDetail && !detail}<p class="chats-empty">Loading run…</p>{/if}
      {#if detail}
        <div class="chat-detail-content">
          <header class="chat-detail-title"><h2>{detail.job_name || "Prompta run"}</h2><p>{nzTime(detail.created_at)}</p></header>
          {#if turnsError}<p class="result-error" role="alert">{turnsError}</p>{/if}
          {#each turns as turn, index (turn.reply_id || detail.send_id)}
            <div class="message-group user-group">
              <div class="message-role">You {#if index === 0}· Job prompt{:else}· Reply {index}{/if}</div>
              <div class="prompt-bubble">
                <div class:collapsed={turn.user_text.length > 280 && !expandedPrompts[(detail?.send_id ?? "") + ":" + index]} class="prompt-message">{turn.user_text}</div>
                {#if turn.user_text.length > 280}
                  <button class="prompt-expand" type="button" aria-expanded={Boolean(expandedPrompts[(detail?.send_id ?? "") + ":" + index])} onclick={(event) => void togglePrompt((detail?.send_id ?? "") + ":" + index, event)}>
                    {expandedPrompts[(detail?.send_id ?? "") + ":" + index] ? "Show less" : "Show full prompt"}
                    <svg class:rotated={expandedPrompts[(detail?.send_id ?? "") + ":" + index]} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
                  </button>
                {/if}
              </div>
              {#if index === 0 && detail.images?.length}
                <div class="chat-attachments" aria-label="Attached images">
                  {#each detail.images as attachment (attachment.url)}
                    <a href={attachment.url} target="_blank" rel="noopener noreferrer" title={attachment.name}>
                      <img src={attachment.url} alt={attachment.name} loading="lazy" />
                    </a>
                  {/each}
                </div>
              {/if}
            </div>
            <div class="message-group assistant-group">
              <div class="message-role">
                <span>Assistant {#if turn.status === "generating"}<span class="capture-live">· Capturing</span>{/if}</span>
                {#if turn.assistant_text}
                  <button class="copy-message" type="button" aria-label={"Copy assistant reply " + (index + 1)} onclick={() => copyText(formatStoredResponse(turn.assistant_text, index === 0 ? detail?.source ?? "" : ""), turn.reply_id || selectedRunId || "")}>
                    {copyState === (turn.reply_id || detail.send_id) ? "Copied" : copyState === "error:" + (turn.reply_id || detail.send_id) ? "Copy failed" : "Copy"}
                  </button>
                {/if}
              </div>
              {#if turn.assistant_text}
                <ResultMarkdown source={turn.assistant_text} captureSource={index === 0 ? detail.source : ""} />
                {#if turn.status !== "completed"}<p class="partial-note">{turn.status === "generating" ? "Partial response · " : ""}{turnStatus(turn.status)}</p>{/if}
              {:else}
                <p class="no-response">{turnStatus(turn.status)}</p>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
      </div>
      {#if detail && turns.at(-1)?.status === "completed" && turns.at(-1)?.conversation_id && turns.at(-1)?.message_id}
        <ChatComposer mode="reply" onSend={sendReply} />
      {:else if detail && turns.length === 1 && turns[0].status === "completed" && turns[0].conversation_id && !turns[0].message_id}
        <div class="chat-reply-status">
          <button type="button" disabled={recoveringReply} onclick={() => void recoverReply()}>
            {recoveringReply ? "Verifying reply…" : "Reply to this chat"}
          </button>
        </div>
      {:else if turns.at(-1)?.status === "prepared"}
        <div class="chat-prepared-action">
          <span>Reply saved locally, not yet sent.</span>
          <button type="button" onclick={() => { const latest = turns.at(-1); if (latest) void sendPreparedReply(latest); }}>Send saved reply</button>
        </div>
      {:else if detail && turns.length > 1}
        <div class="chat-reply-status">{turnStatus(turns.at(-1)?.status || detail.status)}</div>
      {/if}
    {/if}
  </div>
</section>
