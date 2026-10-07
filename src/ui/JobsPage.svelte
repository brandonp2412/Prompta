<script lang="ts">
  import { onMount } from "svelte";

  type Job = {
    name: string;
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
  };

  const pageSize = 10;
  const refreshIntervalMs = 5000;
  let jobs = $state<Job[]>([]);
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
  let loadInFlight = false;
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

  function closeEditor() {
    reset();
    editorOpen = false;
  }

  function beginNew() {
    reset();
    editorOpen = true;
    requestAnimationFrame(() => {
      document.querySelector<HTMLInputElement>(".name-field input")?.focus();
      document.getElementById("job-editor")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
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

  function sameJob(left: Job, right: Job) {
    return (
      left.name === right.name &&
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
      left.last_sent_at === right.last_sent_at
    );
  }

  function applyJobs(nextJobs: Job[]) {
    const unchanged = jobs.length === nextJobs.length && jobs.every((job, index) => sameJob(job, nextJobs[index]));
    if (unchanged) return;

    jobs = nextJobs;
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
    status = "Saving…";

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

  async function submit() {
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
    if (saved) closeEditor();
  }

  function edit(job: Job) {
    editing = job.name;
    name = job.name;
    prompt = job.prompt;
    schedule = job.daily_at ? "daily" : "interval";
    dailyAt = job.daily_at || "09:00";
    interval = String(job.interval_minutes || 40);
    exact = job.exact_interval;
    editorOpen = true;
    requestAnimationFrame(() => {
      document.getElementById("job-editor")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  async function remove(job: Job) {
    if (!window.confirm("Remove “" + job.name + "”?")) return;
    const removed = await command({ action: "remove", name: job.name }, "Removed " + job.name + ".");
    if (removed && editing === job.name) closeEditor();
  }

  async function toggleAll() {
    if (!jobs.length) return;
    const action = allPaused ? "resume_all" : "pause_all";
    const success = allPaused ? "Resumed all jobs." : "Paused all jobs.";
    await command({ action }, success);
  }

  async function clearAll() {
    if (!jobs.length || !window.confirm("Remove all " + String(jobs.length) + " configured jobs?")) return;
    if (await command({ action: "clear" }, "Cleared all scheduled jobs.")) closeEditor();
  }

  onMount(() => {
    void load();
    const timer = window.setInterval(() => void load({ quiet: true }), refreshIntervalMs);
    return () => window.clearInterval(timer);
  });
</script>

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
            {job.paused ? "paused" : job.status || "pending"}
          </span>
          {#if job.status_message}
            <span class="job-message">{job.status_message}</span>
          {/if}
        </div>

        <div class="job-actions" role="cell">
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

  {#if editorOpen}
    <form
      id="job-editor"
      class="job-editor"
      onsubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <div class="editor-heading">
        <div>
          <h2>{editing ? "Edit job" : "New job"}</h2>
          {#if editing}<span>{editing}</span>{/if}
        </div>
        <button class="toolbar-button" type="button" disabled={saving} onclick={closeEditor}>Close</button>
      </div>

      <div class="editor-grid">
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
            <input bind:value={interval} type="number" min="0.1" step="0.1" required />
          </label>
        {:else}
          <label>
            <span>At</span>
            <input bind:value={dailyAt} type="time" required />
          </label>
        {/if}

        <label class="prompt-field">
          <span>Prompt</span>
          <textarea bind:value={prompt} rows="7" required></textarea>
        </label>
      </div>

      <div class="editor-footer">
        {#if schedule === "interval"}
          <label class="checkbox-row">
            <input bind:checked={exact} type="checkbox" />
            <span>Exact interval</span>
          </label>
        {:else}
          <span></span>
        {/if}

        <div class="editor-actions">
          <button class="toolbar-button" type="button" disabled={saving} onclick={closeEditor}>Cancel</button>
          <button class="primary-button" type="submit" disabled={saving}>Save</button>
        </div>
      </div>
    </form>
  {/if}

  <footer class="jobs-footer">
    <button class="row-action danger-text" type="button" disabled={!jobs.length || saving} onclick={() => void clearAll()}>
      Clear all jobs
    </button>
  </footer>
</section>
