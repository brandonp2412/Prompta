<script lang="ts">
  import { onMount, tick, untrack } from "svelte";
  import JobsPage from "./JobsPage.svelte";
  import ResultMarkdown from "./ResultMarkdown.svelte";
  import {
    groupRuns, nzTime, plainPreview, statusLabel, turnStatus,
    type LocalTurn, type ResultStatus, type RunDetail, type RunSummary,
  } from "./resultFormatting";

  let { view, serverName, selectedRunId, onSelect, onNavigate, onNewChat }: {
    view: "jobs" | "chats";
    serverName: string;
    selectedRunId: string | null;
    onSelect: (sendId: string | null) => void;
    onNavigate: (view: "jobs" | "chats") => void;
    onNewChat: () => void;
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
  let expandedPrompts = $state<Record<string, boolean>>({});
  let total = $state(0);
  let page = $state(0);
  let search = $state("");
  let statusFilter = $state<ResultStatus | "">("");
  let detail = $state<RunDetail | null>(null);
  let turns = $state<LocalTurn[]>([]);
  let turnsError = $state("");
  let copyState = $state("");
  let scrollPane: HTMLDivElement;
  let loadingList = $state(true);
  let loadingDetail = $state(false);
  let listError = $state("");
  let detailError = $state("");
  let listGeneration = 0;
  let pinsGeneration = 0;
  let detailGeneration = 0;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;

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
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 15000);
    return () => {
      clearInterval(interval);
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
        <small>{nzTime(activity(item)).split(", ").at(-1)}</small>
      </span>
      <span class="chat-row-meta"><span class={"result-dot status-" + item.status}></span>{statusLabel(item.status)}{#if item.job_name}<span class="chat-job">{item.job_name}</span>{/if}</span>
      <span class="chat-preview">{plainPreview(item.preview) || "No response captured yet"}</span>
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

<section class:drawer-open={drawerOpen} class:show-list={view === "chats" && !selectedRunId} class="chats-layout" aria-label="Prompta local chats and jobs">
  {#if drawerOpen}
    <button type="button" class="drawer-backdrop" aria-label="Close chat sidebar" onclick={() => drawerOpen = false}></button>
  {/if}
  <aside class="chats-sidebar" aria-label="Local chat sidebar">
    <div class="sidebar-brand">
      <div><strong>Prompta</strong><span>{serverName}</span></div>
      <button class="sidebar-close" type="button" aria-label="Close sidebar" onclick={() => drawerOpen = false}>×</button>
    </div>
    <nav class="sidebar-actions" aria-label="Main navigation">
      <button class="sidebar-primary" type="button" onclick={createChat}>
        <span aria-hidden="true">＋</span> New chat
      </button>
      <button class:active={view === "chats"} type="button" onclick={showChats}>
        <span aria-hidden="true">▤</span> Chats
      </button>
      <button class:active={view === "jobs"} type="button" onclick={showJobs}>
        <span aria-hidden="true">▦</span> Jobs
      </button>
    </nav>
    <div class="chats-heading">
      <h2>Recent <span class="chats-count">{total}</span></h2>
      <button class="chats-refresh" type="button" onclick={refresh} aria-label="Refresh local results" title="Refresh local results">↻</button>
    </div>
    <div class="chats-controls">
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
    {#if listError}<div class="result-error" role="alert">{listError}</div>{/if}
    <div class="chats-list">
      {#if pinned.length}
        <div class="chats-date">Pinned</div>
        {#each pinned as item (item.send_id)}{@render chatItem(item)}{/each}
      {/if}
      {#if loadingList && !items.length}
        <p class="chats-empty">Loading local results…</p>
      {:else if !items.length && !pinned.length}
        <p class="chats-empty">{search || statusFilter ? "No runs match these filters." : "No captured job runs yet."}</p>
      {:else}
        {#each groups as group (group.date)}
          <div class="chats-date">{group.date}</div>
          {#each group.items as item (item.send_id)}{@render chatItem(item)}{/each}
        {/each}
      {/if}
    </div>
    <div class="chats-pagination">
      <span>{total ? page * pageSize + 1 : 0}–{Math.min(total, (page + 1) * pageSize)} of {total}</span>
      <div><button disabled={page === 0} onclick={() => movePage(page - 1)}>Previous</button><button disabled={page + 1 >= pageCount} onclick={() => movePage(page + 1)}>Next</button></div>
    </div>
    <div class="sidebar-footnote">Local Prompta runs only</div>
  </aside>

  <div class="chats-detail" bind:this={scrollPane}>
    <div class="workspace-header">
      <button class="sidebar-menu" type="button" aria-label="Open chat sidebar" aria-expanded={drawerOpen} onclick={() => drawerOpen = true}>☰</button>
      <strong>{view === "jobs" ? "Jobs" : (detail?.title || detail?.job_name || "Chats")}</strong>
      <span>{serverName}</span>
    </div>
    {#if view === "jobs"}
      <div class="jobs-workspace"><JobsPage /></div>
    {:else if !selectedRunId}
      <div class="chats-detail-empty"><div class="empty-icon">✦</div><h2>What would you like to revisit?</h2><p>Select a locally captured run from the sidebar, or start a fresh chat.</p><button class="sidebar-primary" onclick={createChat}>New chat</button></div>
    {:else}
      <div class="chat-detail-toolbar">
        <button class="chat-detail-back" onclick={() => onSelect(null)}>‹ <span>All chats</span></button>
        {#if detail}<span class={"result-pill status-" + (turns.at(-1)?.status || detail.status)}>{turns.length > 1 ? "Latest reply · " + turnStatus(turns.at(-1)?.status || detail.status) : statusLabel(detail.status)}</span>{/if}
      </div>
      {#if detailError}<div class="result-error" role="alert">{detailError}</div>{/if}
      {#if loadingDetail && !detail}<p class="chats-empty">Loading run…</p>{/if}
      {#if detail}
        <div class="chat-detail-content">
          <header class="chat-detail-title"><h2>{detail.job_name || "Prompta run"}</h2><p>{nzTime(detail.created_at)} · Prompta job run</p></header>
          {#if turnsError}<p class="result-error" role="alert">{turnsError}</p>{/if}
          {#each turns as turn, index (turn.reply_id || detail.send_id)}
            <div class="message-group user-group">
              <div class="message-role">You {#if index === 0}· Job prompt{:else}· Reply {index}{/if}</div>
              <div class:collapsed={turn.user_text.length > 280 && !expandedPrompts[(detail?.send_id ?? "") + ":" + index]} class="prompt-message">{turn.user_text}</div>
                {#if turn.user_text.length > 280}
                  <button class="prompt-expand" type="button" aria-expanded={Boolean(expandedPrompts[(detail?.send_id ?? "") + ":" + index])} onclick={() => (expandedPrompts[(detail?.send_id ?? "") + ":" + index] = !expandedPrompts[(detail?.send_id ?? "") + ":" + index])}>
                    {expandedPrompts[(detail?.send_id ?? "") + ":" + index] ? "Show less" : "Show full prompt"}
                  </button>
                {/if}
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
                  <button class="copy-message" type="button" aria-label={"Copy assistant reply " + (index + 1)} onclick={() => copyText(turn.assistant_text, turn.reply_id || selectedRunId || "")}>
                    {copyState === (turn.reply_id || detail.send_id) ? "Copied" : copyState === "error:" + (turn.reply_id || detail.send_id) ? "Copy failed" : "Copy"}
                  </button>
                {/if}
              </div>
              {#if turn.assistant_text}
                <ResultMarkdown source={turn.assistant_text} />
                {#if turn.status !== "completed"}<p class="partial-note">{turn.status === "generating" ? "Partial response · " : ""}{turnStatus(turn.status)}</p>{/if}
              {:else}
                <p class="no-response">{turnStatus(turn.status)}</p>
              {/if}
              {#if turn.status === "interrupted" || turn.status === "unavailable" || turn.status === "outcome_unknown"}
                <p class="capture-note">{turnStatus(turn.status)}. No automatic history fetch or retry.</p>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
    {/if}
  </div>
</section>
