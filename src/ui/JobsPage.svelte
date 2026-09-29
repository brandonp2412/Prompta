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
  let jobs = $state<Job[]>([]);
  let page = $state(1);
  let pageCount = $derived(Math.max(1, Math.ceil(jobs.length / pageSize)));
  let pageStart = $derived((page - 1) * pageSize);
  let pageEnd = $derived(Math.min(pageStart + pageSize, jobs.length));
  let visibleJobs = $derived(jobs.slice(pageStart, pageEnd));
  let status = $state("");
  let saving = $state(false);
  let editing = $state("");
  let name = $state("");
  let prompt = $state("");
  let schedule = $state<"interval" | "daily">("interval");
  let interval = $state("40");
  let dailyAt = $state("09:00");
  let exact = $state(false);

  function reset() {
    editing = "";
    name = "";
    prompt = "";
    schedule = "interval";
    interval = "40";
    dailyAt = "09:00";
    exact = false;
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

  function clampPage() {
    page = Math.max(1, Math.min(page, Math.max(1, Math.ceil(jobs.length / pageSize))));
  }

  function changePage(nextPage: number) {
    page = Math.max(1, Math.min(nextPage, pageCount));
    document.getElementById("jobs-title")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function load({ quiet = false }: { quiet?: boolean } = {}) {
    if (!quiet) status = "Loading jobs…";

    try {
      const response = await fetch("./api/jobs", { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status) + " " + response.statusText);

      const result = await response.json();
      jobs = Array.isArray(result.jobs) ? result.jobs : [];
      clampPage();
      if (!quiet) status = String(jobs.length) + " configured job" + (jobs.length === 1 ? "" : "s") + ".";
    } catch (error) {
      status = "Could not load jobs: " + String(error).replace(/^Error:\s*/, "");
    }
  }

  async function command(payload: Record<string, unknown>, success: string) {
    saving = true;
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

      jobs = Array.isArray(result.jobs) ? result.jobs : [];
      clampPage();
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
    if (saved) reset();
  }

  function edit(job: Job) {
    editing = job.name;
    name = job.name;
    prompt = job.prompt;
    schedule = job.daily_at ? "daily" : "interval";
    dailyAt = job.daily_at || "09:00";
    interval = String(job.interval_minutes || 40);
    exact = job.exact_interval;
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }

  async function remove(job: Job) {
    if (!window.confirm("Remove “" + job.name + "”?")) return;
    const removed = await command({ action: "remove", name: job.name }, "Removed " + job.name + ".");
    if (removed && editing === job.name) reset();
  }

  async function clearAll() {
    if (!jobs.length || !window.confirm("Remove all " + String(jobs.length) + " configured jobs?")) return;
    if (await command({ action: "clear" }, "Cleared all scheduled jobs.")) reset();
  }

  onMount(() => {
    void load();
    const timer = window.setInterval(() => void load({ quiet: true }), 5000);
    return () => window.clearInterval(timer);
  });
</script>

<section class="jobs-panel" aria-labelledby="jobs-title">
  <div class="section-heading">
    <div>
      <h1 id="jobs-title">Scheduled jobs</h1>
      <p>{jobs.length} configured</p>
    </div>
    <div class="heading-actions">
      <span class="status-line" role="status" aria-live="polite">{status}</span>
      <button class="text-button" type="button" disabled={saving} onclick={() => void load()}>
        Refresh
      </button>
    </div>
  </div>

  <div class="jobs-list">
    {#if jobs.length === 0}
      <div class="empty-row">No scheduled jobs.</div>
    {/if}

    {#each visibleJobs as job (job.name)}
      <article class="job-row">
        <div class="job-content">
          <div class="job-title-line">
            <h2>{job.name}</h2>
            <span class:error={job.status === "failing"} class:paused={job.paused} class="job-status">
              {job.paused ? "paused" : job.status || "pending"}
            </span>
            <span class="job-schedule">{scheduleText(job)}</span>
          </div>

          <div class="job-prompt">{job.prompt}</div>

          <div class="job-meta">
            <span><strong>Next</strong> {job.paused ? "Paused" : formatDate(job.next_due_at_epoch)}</span>
            <span><strong>Last sent</strong> {formatDate(job.last_sent_at)}</span>
            {#if job.source_revision}
              <span title={job.source_revision}><strong>Rev</strong> {job.source_revision.slice(0, 8)}</span>
            {/if}
          </div>

          {#if job.status_message}
            <p class="job-message">{job.status_message}</p>
          {/if}
        </div>

        <div class="job-actions">
          {#if !job.run_at_epoch}
            <button class="text-button" type="button" disabled={saving} onclick={() => edit(job)}>
              Edit
            </button>
          {/if}
          <button
            class="text-button"
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
          <button class="text-button danger-text" type="button" disabled={saving} onclick={() => void remove(job)}>
            Remove
          </button>
        </div>
      </article>
    {/each}
  </div>

  {#if jobs.length > pageSize}
    <nav class="pagination" aria-label="Job pages">
      <span>{pageStart + 1}–{pageEnd} of {jobs.length} · Page {page} of {pageCount}</span>
      <div class="pagination-actions">
        <button class="text-button" type="button" disabled={page <= 1} onclick={() => changePage(page - 1)}>
          Previous
        </button>
        <button
          class="text-button"
          type="button"
          disabled={page >= pageCount}
          onclick={() => changePage(page + 1)}
        >
          Next
        </button>
      </div>
    </nav>
  {/if}

  <form
    class="job-form"
    onsubmit={(event) => {
      event.preventDefault();
      void submit();
    }}
  >
    <div class="form-heading">
      <div>
        <h2>{editing ? "Edit " + editing : "Add job"}</h2>
        <p>{editing ? "Update the prompt or schedule." : "Create a recurring scheduled prompt."}</p>
      </div>
    </div>

    <div class="form-fields">
      <label class="name-field">
        <span>Name</span>
        <input bind:value={name} autocomplete="off" readonly={Boolean(editing)} required />
      </label>

      <label class="prompt-field">
        <span>Prompt</span>
        <textarea bind:value={prompt} rows="4" required></textarea>
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
    </div>

    <div class="form-footer">
      {#if schedule === "interval"}
        <label class="checkbox-row">
          <input bind:checked={exact} type="checkbox" />
          <span>Exact interval</span>
        </label>
      {:else}
        <span></span>
      {/if}

      <div class="form-actions">
        <button class="text-button" type="button" disabled={saving} onclick={reset}>
          {editing ? "Cancel" : "Reset"}
        </button>
        <button class="primary-button" type="submit" disabled={saving}>Save job</button>
      </div>
    </div>
  </form>

  <div class="danger-zone">
    <button class="text-button danger-text" type="button" disabled={!jobs.length || saving} onclick={() => void clearAll()}>
      Clear all jobs
    </button>
  </div>
</section>
