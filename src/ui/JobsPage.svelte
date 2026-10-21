<script lang="ts">
  import { onMount } from "svelte";
  import { sortJobs } from "./jobSorting";

  type Job = {
    name: string;
    created_order: number;
    prompt: string;
    status: string;
    status_message: string;
    paused: boolean;
    run_at_epoch: number | null;
    daily_at: string | null;
    interval_minutes: number;
    exact_interval: boolean;
    source_revision: string;
    next_due_at_epoch: number;
    last_sent_at: number;
    last_uncertain_send_at: number;
  };

  type DeliveryCounts = {
    succeeded: number;
    dead_lettered: number;
    outcome_unknown: number;
  };

  type EditorRoute = { kind: "new" } | { kind: "edit"; name: string };

  const pageSize = 10;
  const refreshIntervalMs = 5000;
  let jobs = $state<Job[]>([]);
  let deliveryCounts = $state<DeliveryCounts>({ succeeded: 0, dead_lettered: 0, outcome_unknown: 0 });
  let page = $state(1);
  let pageCount = $derived(Math.max(1, Math.ceil(jobs.length / pageSize)));
  let pageStart = $derived((page - 1) * pageSize);
  let pageEnd = $derived(Math.min(pageStart + pageSize, jobs.length));
  let visibleJobs = $derived(jobs.slice(pageStart, pageEnd));
  let allPaused = $derived(jobs.length > 0 && jobs.every((job) => job.paused));
  let pausedCount = $derived(jobs.filter((job) => job.paused).length);
  let status = $state("");
  let saving = $state(false);
  let editing = $state("");
  let name = $state("");
  let prompt = $state("");
  let schedule = $state<"interval" | "daily">("interval");
  let interval = $state("40");
  let dailyAt = $state("09:00");
  let exact = $state(false);
  let editorOpen = $state(false);
  let editorPage = $state<HTMLElement>();
  let activeEditorRoute = "";
  let listScrollY = 0;
  let editorError = $state("");
  let confirmDiscard = $state(false);
  let initialForm = $state("");
  let dirty = $derived(editorOpen && formSnapshot() !== initialForm);
  let duplicateName = $derived(!editing && jobs.some((job) => job.name === name.trim()));
  let promptCharacters = $derived(prompt.length);
  let promptLines = $derived(prompt ? prompt.split("\n").length : 0);
  let loadInFlight = false;
  let healthLoadInFlight = false;
  let dataGeneration = 0;

  function reset() {
    editing = "";
    name = "";
    prompt = "";
    schedule = "interval";
    interval = "40";
    dailyAt = "09:00";
    exact = false;
  }

  function formSnapshot() {
    return JSON.stringify({ name, prompt, schedule, interval, dailyAt, exact });
  }

  function closeEditorState() {
    editorOpen = false;
    activeEditorRoute = "";
    confirmDiscard = false;
    editorError = "";
    reset();
  }

  function editorRouteFromUrl(): EditorRoute | null {
    const url = new URL(window.location.href);
    if (url.searchParams.has("new")) return { kind: "new" };
    const jobName = url.searchParams.get("edit");
    return jobName === null ? null : { kind: "edit", name: jobName };
  }

  function routeKey(route: EditorRoute | null) {
    return route?.kind === "new" ? "new" : route?.kind === "edit" ? "edit:" + route.name : "";
  }

  function jobsUrl() {
    const url = new URL(window.location.href);
    url.searchParams.delete("new");
    url.searchParams.delete("edit");
    return url;
  }

  function leaveEditor() {
    if (window.history.state?.promptaEditor === true) {
      window.history.back();
    } else {
      window.history.replaceState(null, "", jobsUrl());
      closeEditorState();
      requestAnimationFrame(() => window.scrollTo(0, listScrollY));
    }
  }

  function requestClose() {
    if (saving) return;
    if (dirty) {
      confirmDiscard = true;
      return;
    }
    leaveEditor();
  }

  function discardEditor() {
    initialForm = formSnapshot();
    leaveEditor();
  }

  function openEditor(focusName: boolean) {
    editorError = "";
    confirmDiscard = false;
    initialForm = formSnapshot();
    editorOpen = true;
    requestAnimationFrame(() => {
      window.scrollTo(0, 0);
      if (focusName) {
        editorPage?.querySelector<HTMLInputElement>(".name-field input")?.focus();
      } else if (window.matchMedia("(pointer: coarse)").matches) {
        editorPage?.focus();
      } else {
        const textarea = editorPage?.querySelector<HTMLTextAreaElement>(".prompt-field textarea");
        textarea?.focus();
        textarea?.setSelectionRange(0, 0);
      }
    });
  }

  function showEditor(route: EditorRoute) {
    if (route.kind === "new") {
      reset();
    } else {
      const job = jobs.find((item) => item.name === route.name);
      if (!job) {
        status = "Job not found: " + route.name;
        window.history.replaceState(null, "", jobsUrl());
        closeEditorState();
        return;
      }
      editing = job.name;
      name = job.name;
      prompt = job.prompt;
      schedule = job.daily_at ? "daily" : "interval";
      dailyAt = job.daily_at || "09:00";
      interval = String(job.interval_minutes || 40);
      exact = job.exact_interval;
    }
    activeEditorRoute = routeKey(route);
    openEditor(route.kind === "new");
  }

  function pushEditor(route: EditorRoute) {
    listScrollY = window.scrollY;
    const url = jobsUrl();
    if (route.kind === "new") url.searchParams.set("new", "1");
    else url.searchParams.set("edit", route.name);
    window.history.pushState({ promptaEditor: true }, "", url);
    showEditor(route);
  }

  function syncEditorFromUrl() {
    const route = editorRouteFromUrl();
    if (routeKey(route) === activeEditorRoute) return;
    if (saving || (dirty && !window.confirm("Discard unsaved job changes?"))) {
      window.history.forward();
      return;
    }
    if (route) showEditor(route);
    else {
      closeEditorState();
      requestAnimationFrame(() => window.scrollTo(0, listScrollY));
    }
  }

  function beginNew() {
    pushEditor({ kind: "new" });
  }

  function onEditorKeydown(event: KeyboardEvent) {
    if (!editorOpen || saving) return;
    if (event.key === "Escape") {
      event.preventDefault();
      requestClose();
      return;
    }
    if (!dirty || duplicateName) return;
    if (!(event.ctrlKey || event.metaKey) || event.key !== "Enter") return;
    if (!(event.target instanceof Node) || !editorPage?.contains(event.target)) return;
    event.preventDefault();
    editorPage.querySelector<HTMLFormElement>("#job-editor")?.requestSubmit();
  }

  function formatDate(epoch: number) {
    if (!epoch) return "—";
    return new Date(epoch * 1000).toLocaleString([], {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function scheduleText(job: Job) {
    if (job.run_at_epoch) return "once · " + formatDate(job.run_at_epoch);
    if (job.daily_at) return "daily · " + job.daily_at;

    const minutes = Number(job.interval_minutes);
    const amount =
      minutes >= 60 && minutes % 60 === 0
        ? String(minutes / 60) + " hour" + (minutes === 60 ? "" : "s")
        : String(minutes) + " minute" + (minutes === 1 ? "" : "s");
    return "every " + amount + (job.exact_interval ? " · exact" : "");
  }

  function jobStateText(job: Job) {
    if (job.paused) return "paused";
    if (
      job.last_uncertain_send_at > job.last_sent_at ||
      (job.status === "failing" && /lost send confirmation after dispatch/i.test(job.status_message))
    ) return "unconfirmed";
    return job.status || "pending";
  }

  function sameJob(left: Job, right: Job) {
    return (
      left.name === right.name &&
      left.created_order === right.created_order &&
      left.prompt === right.prompt &&
      left.status === right.status &&
      left.status_message === right.status_message &&
      left.paused === right.paused &&
      left.run_at_epoch === right.run_at_epoch &&
      left.daily_at === right.daily_at &&
      left.interval_minutes === right.interval_minutes &&
      left.exact_interval === right.exact_interval &&
      left.source_revision === right.source_revision &&
      left.next_due_at_epoch === right.next_due_at_epoch &&
      left.last_sent_at === right.last_sent_at &&
      left.last_uncertain_send_at === right.last_uncertain_send_at
    );
  }

  function applyJobs(nextJobs: Job[]) {
    const sortedJobs = sortJobs(nextJobs);
    const unchanged = jobs.length === sortedJobs.length && jobs.every((job, index) => sameJob(job, sortedJobs[index]));
    if (unchanged) return;

    jobs = sortedJobs;
    clampPage();
  }

  function clampPage() {
    page = Math.max(1, Math.min(page, Math.max(1, Math.ceil(jobs.length / pageSize))));
  }

  function changePage(nextPage: number) {
    page = Math.max(1, Math.min(nextPage, pageCount));
    document.getElementById("jobs-title")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function load({ quiet = false }: { quiet?: boolean } = {}) {
    if (loadInFlight || (quiet && document.visibilityState !== "visible")) return;

    loadInFlight = true;
    const requestGeneration = dataGeneration;
    if (!quiet) status = "Loading jobs…";

    try {
      const response = await fetch("./api/jobs", { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status) + " " + response.statusText);

      const result = await response.json();
      if (requestGeneration !== dataGeneration) return;

      const nextJobs: Job[] = Array.isArray(result.jobs) ? result.jobs : [];
      applyJobs(nextJobs);
      if (!quiet) status = String(jobs.length) + " configured job" + (jobs.length === 1 ? "" : "s") + ".";
    } catch (error) {
      if (!quiet) status = "Could not load jobs: " + String(error).replace(/^Error:\s*/, "");
    } finally {
      loadInFlight = false;
    }
  }

  async function command(payload: Record<string, unknown>, success: string) {
    saving = true;
    dataGeneration += 1;
    status = payload.action === "fire_now" ? "Queuing fresh chat…" : "Saving…";

    try {
      const response = await fetch("./api/jobs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(String(result.error || String(response.status) + " " + response.statusText));
      }

      const nextJobs: Job[] = Array.isArray(result.jobs) ? result.jobs : [];
      applyJobs(nextJobs);
      status = success;
      return true;
    } catch (error) {
      status = "Job update failed: " + String(error).replace(/^Error:\s*/, "");
      return false;
    } finally {
      saving = false;
    }
  }

  async function loadDeliveryCounts() {
    if (healthLoadInFlight || document.visibilityState !== "visible") return;
    healthLoadInFlight = true;
    try {
      const response = await fetch("./api/health", { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status) + " " + response.statusText);
      const result = await response.json();
      const queue = result.queue;
      if (queue && typeof queue === "object") {
        deliveryCounts = {
          succeeded: Number.isSafeInteger(queue.succeeded) ? queue.succeeded : 0,
          dead_lettered: Number.isSafeInteger(queue.dead_lettered) ? queue.dead_lettered : 0,
          outcome_unknown: Number.isSafeInteger(queue.outcome_unknown) ? queue.outcome_unknown : 0,
        };
      }
    } catch {
      // Keep the latest counts visible if a background health refresh fails.
    } finally {
      healthLoadInFlight = false;
    }
  }

  async function submit() {
    if (saving || !dirty || duplicateName) return;
    editorError = "";
    const jobName = name.trim();
    const jobPrompt = prompt.trim();
    if (!jobName || !jobPrompt) return;

    const daily = schedule === "daily";
    const saved = await command(
      {
        action: "add",
        name: jobName,
        prompt: jobPrompt,
        daily_at: daily ? dailyAt : "",
        interval_minutes: daily ? null : Number(interval),
        exact_interval: !daily && exact,
      },
      "Saved " + jobName + ".",
    );
    if (saved) {
      initialForm = formSnapshot();
      leaveEditor();
    } else editorError = status;
  }

  function edit(job: Job) {
    pushEditor({ kind: "edit", name: job.name });
  }

  async function remove(job: Job) {
    if (!window.confirm("Remove “" + job.name + "”?")) return;
    const removed = await command({ action: "remove", name: job.name }, "Removed " + job.name + ".");
    if (removed && editing === job.name) leaveEditor();
  }

  async function toggleAll() {
    if (!jobs.length) return;
    const action = allPaused ? "resume_all" : "pause_all";
    const success = allPaused ? "Resumed all jobs." : "Paused all jobs.";
    await command({ action }, success);
  }

  async function clearAll() {
    if (!jobs.length || !window.confirm("Remove all " + String(jobs.length) + " configured jobs?")) return;
    if (await command({ action: "clear" }, "Cleared all scheduled jobs.") && editorOpen) leaveEditor();
  }

  onMount(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    void load().then(syncEditorFromUrl);
    void loadDeliveryCounts();
    window.addEventListener("popstate", syncEditorFromUrl);
    const timer = window.setInterval(() => {
      void load({ quiet: true });
      void loadDeliveryCounts();
    }, refreshIntervalMs);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("beforeunload", onBeforeUnload);
      window.removeEventListener("popstate", syncEditorFromUrl);
    };
  });
</script>

<svelte:window onkeydown={onEditorKeydown} />

{#if !editorOpen}
<section class="jobs-panel" aria-labelledby="jobs-title">
  <div class="jobs-toolbar">
    <div class="toolbar-title">
      <h1 id="jobs-title">Jobs</h1>
      <span>{jobs.length}</span>
    </div>

    <div class="toolbar-actions">
      <span class="status-line" role="status" aria-live="polite">{status}</span>

      <button
        class:active={!allPaused}
        class="master-toggle"
        type="button"
        role="switch"
        aria-checked={!allPaused}
        disabled={!jobs.length || saving}
        title={allPaused ? "Resume all jobs" : "Pause all jobs"}
        onclick={() => void toggleAll()}
      >
        <span class="switch-track"><span class="switch-knob"></span></span>
        <span>{allPaused ? "Resume all" : "Pause all"}</span>
      </button>

      <button class="toolbar-button" type="button" disabled={saving} onclick={() => void load()}>Refresh</button>
      <button class="primary-button" type="button" disabled={saving} onclick={beginNew}>New job</button>
    </div>
  </div>

  <div class="jobs-summary">
    <span>{jobs.length - pausedCount} running</span>
    <span>{pausedCount} paused</span>
    <span>{deliveryCounts.succeeded} succeeded</span>
    <span>{deliveryCounts.dead_lettered} failed</span>
    <span>{deliveryCounts.outcome_unknown} unconfirmed</span>
    {#if jobs.length > pageSize}
      <span>{pageStart + 1}–{pageEnd} shown</span>
    {/if}
  </div>

  <div class="jobs-table" role="table" aria-label="Scheduled jobs">
    <div class="jobs-table-head" role="row">
      <span role="columnheader">Job</span>
      <span role="columnheader">Schedule</span>
      <span role="columnheader">Next run</span>
      <span role="columnheader">State</span>
      <span role="columnheader" class="actions-heading">Actions</span>
    </div>

    {#if jobs.length === 0}
      <div class="empty-row">No scheduled jobs.</div>
    {/if}

    {#each visibleJobs as job (job.name)}
      <div class="job-row" role="row">
        <div class="job-main" role="cell">
          <div class="job-name">{job.name}</div>
          <div class="job-prompt" title={job.prompt}>{job.prompt}</div>
          <div class="job-submeta">
            <span>Last sent {formatDate(job.last_sent_at)}</span>
            {#if job.source_revision}
              <span title={job.source_revision}>rev {job.source_revision.slice(0, 8)}</span>
            {/if}
          </div>
        </div>

        <div class="job-cell schedule-cell" role="cell">
          <span class="cell-label">Schedule</span>
          <span>{scheduleText(job)}</span>
        </div>

        <div class="job-cell" role="cell">
          <span class="cell-label">Next run</span>
          <span>{job.paused ? "Paused" : formatDate(job.next_due_at_epoch)}</span>
        </div>

        <div class="job-cell state-cell" role="cell">
          <span class="cell-label">State</span>
          <span class:error={job.status === "failing"} class="state-value">
            <span class="state-dot"></span>
            {jobStateText(job)}
          </span>
          {#if job.status_message}
            <span class="job-message">{job.status_message}</span>
          {/if}
        </div>

        <div class="job-actions" role="cell">
          <button
            class="row-action"
            type="button"
            disabled={saving}
            title={job.daily_at || job.run_at_epoch ? "Launch a fresh chat without moving the fixed schedule" : "Launch a fresh chat and restart the interval countdown"}
            onclick={() => void command({ action: "fire_now", name: job.name }, "Queued one fresh chat for " + job.name + ".")}
          >Fire now</button>
          {#if !job.run_at_epoch}
            <button class="row-action" type="button" disabled={saving} onclick={() => edit(job)}>Edit</button>
          {/if}
          <button
            class="row-action"
            type="button"
            disabled={saving}
            onclick={() =>
              void command(
                { action: job.paused ? "resume" : "pause", name: job.name },
                (job.paused ? "Resumed " : "Paused ") + job.name + ".",
              )}
          >
            {job.paused ? "Resume" : "Pause"}
          </button>
          <button class="row-action danger-text" type="button" disabled={saving} onclick={() => void remove(job)}>
            Remove
          </button>
        </div>
      </div>
    {/each}
  </div>

  {#if jobs.length > pageSize}
    <nav class="pagination" aria-label="Job pages">
      <span>Page {page} of {pageCount}</span>
      <div class="pagination-actions">
        <button class="toolbar-button" type="button" disabled={page <= 1} onclick={() => changePage(page - 1)}>
          Previous
        </button>
        <button class="toolbar-button" type="button" disabled={page >= pageCount} onclick={() => changePage(page + 1)}>
          Next
        </button>
      </div>
    </nav>
  {/if}

  <footer class="jobs-footer">
    <button class="row-action danger-text" type="button" disabled={!jobs.length || saving} onclick={() => void clearAll()}>
      Clear all jobs
    </button>
  </footer>

</section>
{/if}

{#if editorOpen}
  <section bind:this={editorPage} class="editor-page" aria-labelledby="editor-title" tabindex="-1">
      <form
        id="job-editor"
        class="job-editor"
        onsubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div class="editor-heading">
          <button class="toolbar-button editor-back" type="button" disabled={saving} onclick={requestClose}>← Jobs</button>
          <div class="editor-title">
            <h2 id="editor-title">{editing ? "Edit job" : "New job"}</h2>
            {#if editing}<span title={editing}>{editing}</span>{/if}
          </div>
        </div>

        <div class="editor-body">
          <div class="editor-settings">
            <label class="name-field">
              <span>Name</span>
              <input bind:value={name} autocomplete="off" readonly={Boolean(editing)} required />
            </label>

            <label>
              <span>Schedule</span>
              <select bind:value={schedule}>
                <option value="interval">Interval</option>
                <option value="daily">Daily</option>
              </select>
            </label>

            {#if schedule === "interval"}
              <label>
                <span>Every (minutes)</span>
                <input bind:value={interval} type="number" min="0.1" max="43200" step="0.1" required />
              </label>
            {:else}
              <label>
                <span>At (local time)</span>
                <input bind:value={dailyAt} type="time" required />
              </label>
            {/if}
          </div>

          {#if schedule === "interval"}
            <label class="checkbox-row">
              <input bind:checked={exact} type="checkbox" />
              <span>Exact interval</span>
            </label>
          {/if}

          <label class="prompt-field">
            <span>Prompt</span>
            <textarea bind:value={prompt} rows="14" required></textarea>
          </label>
          <div class="prompt-counter">{promptCharacters.toLocaleString()} characters · {promptLines.toLocaleString()} lines</div>
        </div>

        <div class="editor-footer">
          <div class="editor-feedback" role="status" aria-live="polite">
            {#if confirmDiscard}
              <span>Discard unsaved changes?</span>
              <button class="toolbar-button" type="button" onclick={() => (confirmDiscard = false)}>Keep editing</button>
              <button class="toolbar-button danger-text" type="button" onclick={discardEditor}>Discard</button>
            {:else if editorError}
              <span class="editor-error">{editorError}</span>
            {:else if duplicateName}
              <span class="editor-error">This job already exists. Choose another name.</span>
            {:else if dirty}
              <span>Unsaved changes</span>
            {:else if editing}
              <span>No changes</span>
            {/if}
          </div>
          <div class="editor-actions">
            <span class="keyboard-hint">Ctrl/⌘ + Enter to save</span>
            <button class="toolbar-button" type="button" disabled={saving} onclick={requestClose}>Cancel</button>
            <button class="primary-button" type="submit" disabled={saving || !dirty || duplicateName}>
              {saving ? "Saving…" : editing ? "Save changes" : "Create job"}
            </button>
          </div>
        </div>
      </form>
  </section>
{/if}
