<script lang="ts">
  import { onMount, untrack } from "svelte";
  import ResultMarkdown from "./ResultMarkdown.svelte";
  import {
    groupRuns, nzTime, plainPreview, statusLabel,
    type ResultStatus, type RunDetail, type RunSummary,
  } from "./resultFormatting";

  let { selectedRunId, onSelect }: {
    selectedRunId: string | null;
    onSelect: (sendId: string | null) => void;
  } = $props();

  const pageSize = 20;
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
  let total = $state(0);
  let page = $state(0);
  let search = $state("");
  let statusFilter = $state<ResultStatus | "">("");
  let detail = $state<RunDetail | null>(null);
  let loadingList = $state(true);
  let loadingDetail = $state(false);
  let listError = $state("");
  let detailError = $state("");
  let lastRefresh = $state(0);
  let listGeneration = 0;
  let detailGeneration = 0;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  let groups = $derived(groupRuns(items));
  let pageCount = $derived(Math.min(5001, Math.max(1, Math.ceil(total / pageSize))));

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
      lastRefresh = Date.now();
    } catch {
      if (generation === listGeneration) listError = "Local results are temporarily unavailable.";
    } finally {
      if (generation === listGeneration) loadingList = false;
    }
  }

  async function loadDetail(id: string) {
    const generation = ++detailGeneration;
    if (detail?.send_id !== id) detail = null;
    loadingDetail = true;
    try {
      const response = await fetch("./api/results/" + encodeURIComponent(id), { cache: "no-store" });
      if (!response.ok) throw new Error("Result not found");
      const body: RunDetail = await response.json();
      if (generation !== detailGeneration) return;
      detail = body;
      detailError = "";
    } catch {
      if (generation === detailGeneration) detailError = "This run is unavailable locally.";
    } finally {
      if (generation === detailGeneration) loadingDetail = false;
    }
  }

  function refresh() {
    void loadList();
    if (selectedRunId) void loadDetail(selectedRunId);
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

  $effect(() => {
    const id = selectedRunId;
    // Only a selected-run change should fetch; loadDetail also reads/writes reactive detail.
    untrack(() => {
      if (id) void loadDetail(id);
      else {
        detailGeneration += 1;
        detail = null;
        detailError = "";
      }
    });
  });

  onMount(() => {
    void loadList();
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 15000);
    return () => {
      clearInterval(interval);
      clearTimeout(searchTimer);
    };
  });
</script>

<section class:detail-open={selectedRunId !== null} class="chats-layout" aria-label="Prompta job results">
  <div class="chats-sidebar">
    <div class="chats-heading">
      <div>
        <h1>Chats <span class="chats-count">{total}</span></h1>
        <p>Read-only results from Prompta job runs</p>
      </div>
      <button class="chats-refresh" onclick={refresh} aria-label="Refresh local results" title="Refresh local results">↻</button>
    </div>
    <div class="chats-controls">
      <label class="search-label">
        <span class="sr-only">Search job results</span>
        <input type="search" placeholder="Search runs or responses" bind:value={search} oninput={searchChanged} />
      </label>
      <label>
        <span class="sr-only">Filter results by state</span>
        <select bind:value={statusFilter} onchange={applyFilter}>
          {#each statuses as choice}<option value={choice.value}>{choice.label}</option>{/each}
        </select>
      </label>
    </div>
    {#if listError}<div class="result-error" role="alert">{listError}</div>{/if}
    {#if loadingList && !items.length}
      <p class="chats-empty">Loading local results…</p>
    {:else if !items.length}
      <p class="chats-empty">{search || statusFilter ? "No runs match these filters." : "No captured job runs yet."}</p>
    {:else}
      <div class="chats-list">
        {#each groups as group (group.date)}
          <div class="chats-date">{group.date}</div>
          {#each group.items as item (item.send_id)}
            <button
              class:chosen={selectedRunId === item.send_id}
              class="chat-row" onclick={() => onSelect(item.send_id)}
              aria-current={selectedRunId === item.send_id ? "true" : undefined}
            >
              <span class="chat-row-top"><strong>{item.title || "Untitled run"}</strong><small>{nzTime(item.created_at).split(", ").at(-1)}</small></span>
              <span class="chat-row-meta"><span class={"result-dot status-" + item.status}></span>{statusLabel(item.status)}{#if item.job_name}<span class="chat-job">{item.job_name}</span>{/if}</span>
              <span class="chat-preview">{plainPreview(item.preview) || "No response captured yet"}</span>
            </button>
          {/each}
        {/each}
      </div>
    {/if}
    <div class="chats-pagination">
      <span>{total ? page * pageSize + 1 : 0}–{Math.min(total, (page + 1) * pageSize)} of {total}</span>
      <div><button disabled={page === 0} onclick={() => movePage(page - 1)}>Previous</button><button disabled={page + 1 >= pageCount} onclick={() => movePage(page + 1)}>Next</button></div>
    </div>
  </div>

  <div class="chats-detail">
    {#if !selectedRunId}
      <div class="chats-detail-empty"><div class="empty-icon">✦</div><h2>Select a run</h2><p>View the original job prompt and its captured assistant response.</p></div>
    {:else}
      <div class="chat-detail-toolbar">
        <button class="chat-detail-back" onclick={() => onSelect(null)}>‹ <span>All chats</span></button>
        {#if detail}<span class={"result-pill status-" + detail.status}>{statusLabel(detail.status)}</span>{/if}
      </div>
      {#if detailError}<div class="result-error" role="alert">{detailError}</div>{/if}
      {#if loadingDetail && !detail}<p class="chats-empty">Loading run…</p>{/if}
      {#if detail}
        <div class="chat-detail-content">
          <header class="chat-detail-title"><h2>{detail.job_name || "Prompta run"}</h2><p>{nzTime(detail.created_at)} · Prompta job run</p></header>
          <div class="message-group"><div class="message-role">You · Job prompt</div><div class="prompt-message">{detail.user_text}</div></div>
          <div class="message-group assistant-group">
            <div class="message-role">Assistant {#if detail.status === "generating"}<span class="capture-live">· Capturing</span>{/if}</div>
            {#if detail.assistant_text}
              <ResultMarkdown source={detail.assistant_text} />
              {#if detail.status !== "completed"}<p class="partial-note">Partial response · {statusLabel(detail.status).toLowerCase()}</p>{/if}
            {:else}
              <p class="no-response">{detail.status === "accepted" || detail.status === "queued" ? "Awaiting a captured response…" : detail.status === "generating" ? "Response is generating…" : "No assistant response was captured for this run."}</p>
            {/if}
          </div>
          {#if detail.status === "interrupted" || detail.status === "unavailable"}
            <p class="capture-note">Capture {detail.status}. No historical chat will be reopened or retried.</p>
          {/if}
        </div>
      {/if}
    {/if}
  </div>
</section>
