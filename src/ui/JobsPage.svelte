<script lang="ts">
  import { dialogVisibility } from "./browserAttachments.svelte";
  import { formatClockTime12Hour, formatDailyTime12Hour, postJsonRequest } from "./clientLogic";
  import { jobPromptIsExpandable, paginateJobs } from "./jobs";

  type Job = {
    name: string;
    prompt?: string;
    status?: string;
    paused?: boolean;
    run_at_epoch?: number;
    daily_at?: string;
    interval_minutes?: number;
    exact_interval?: boolean;
    source_revision?: string;
  };

  let jobs = $state.raw<Job[]>([]);
  let page = $state(1);
  let status = $state("");
  let saving = $state(false);
  let editing = $state("");
  let name = $state("");
  let prompt = $state("");
  let schedule = $state("interval");
  let interval = $state("40");
  let dailyAt = $state("09:00");
  let exact = $state(false);
  let confirmation = $state<
    | { kind: "remove"; job: Job }
    | { kind: "clear"; count: number }
    | null
  >(null);
  const pagination = $derived(paginateJobs(jobs, page));

  function reset() {
    editing = "";
    name = "";
    prompt = "";
    schedule = "interval";
    interval = "40";
    dailyAt = "09:00";
    exact = false;
  }

  function scheduleText(job: Job) {
    if (job.run_at_epoch) {
      const date = new Date(job.run_at_epoch * 1000);
      return `once · ${date.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" })} ${formatClockTime12Hour(date)}`;
    }

    if (job.daily_at) return `daily · ${formatDailyTime12Hour(job.daily_at)}`;

    const minutes = Number(job.interval_minutes);
    const value =
      minutes >= 60 && minutes % 60 === 0
        ? `${minutes / 60} hour${minutes === 60 ? "" : "s"}`
        : `${minutes} minute${minutes === 1 ? "" : "s"}`;

    return `every ${value}${job.exact_interval ? " · exact" : ""}`;
  }

  async function load() {
    status = "Loading jobs…";

    try {
      const response = await fetch("api/jobs", { cache: "no-store" });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);

      const result = await response.json();
      jobs = Array.isArray(result.jobs) ? result.jobs : [];
      page = 1;
      status = `${jobs.length} configured job${jobs.length === 1 ? "" : "s"}.`;
    } catch (error) {
      status = `Could not load jobs: ${String(error).replace(/^Error:\s*/, "")}`;
    }
  }

  async function command(payload: Record<string, unknown>, success: string) {
    status = "Running Prompta CLI command…";
    saving = true;

    try {
      const result = await postJsonRequest("api/jobs", payload);
      jobs = Array.isArray(result.jobs) ? result.jobs : [];
      page = paginateJobs(jobs, page).page;
      const invoked = Array.isArray(result.command) ? result.command.join(" ") : "";
      status = invoked ? `${success} · ${invoked}` : success;
      return true;
    } catch (error) {
      status = `Jobs command failed: ${String(error).replace(/^Error:\s*/, "")}`;
      return false;
    } finally {
      saving = false;
    }
  }

  async function submit() {
    const daily = schedule === "daily";

    if (
      await command(
        {
          action: "add",
          name: name.trim(),
          prompt: prompt.trim(),
          daily_at: daily ? dailyAt : "",
          interval_minutes: daily ? null : Number(interval),
          exact_interval: !daily && exact,
        },
        `Saved ${name.trim()}`,
      )
    ) {
      reset();
    }
  }

  function edit(job: Job) {
    editing = job.name;
    name = job.name;
    prompt = job.prompt || "";
    schedule = job.daily_at ? "daily" : "interval";
    dailyAt = job.daily_at || "09:00";
    interval = String(job.interval_minutes || 40);
    exact = Boolean(job.exact_interval);
  }

  function requestRemove(job: Job) {
    confirmation = { kind: "remove", job };
  }

  function requestClear() {
    if (!jobs.length) return;

    confirmation = { kind: "clear", count: jobs.length };
  }

  function cancelConfirmation() {
    confirmation = null;
  }

  async function confirmDestructiveAction() {
    const pending = confirmation;
    confirmation = null;
    if (!pending) return;

    if (pending.kind === "clear") {
      if (await command({ action: "clear" }, "Cleared all scheduled jobs")) reset();
      return;
    }

    const job = pending.job;
    if (await command({ action: "remove", name: job.name }, `Removed ${job.name}`)) {
      if (editing === job.name) reset();
    }
  }

  $effect(() => {
    reset();
    void load();
  });
</script>

<section class="jobs-page" aria-labelledby="jobsPageTitle">
  <div class="jobs-page-shell">
    <header class="jobs-page-header">
      <div class="chat-heading">
        <div class="heading-title" id="jobsPageTitle">Scheduled jobs</div>
        <div class="heading-meta">Create and manage scheduled prompts.</div>
      </div>
    </header>

    <div class="jobs-page-status" role="status">{status}</div>

    <div class="jobs-list">
      {#if !jobs.length}<div class="jobs-empty">No scheduled jobs.</div>{/if}

      {#each pagination.items as job (job.name)}
        <article class="job-row">
          <div class="job-row-top">
            <div>
              <div class="job-row-name">{job.name}</div>
              <div class="job-row-meta">
                {scheduleText(job)}
                {#if job.source_revision}
                  · rev <span title={job.source_revision}>{job.source_revision.slice(0, 8)}</span>
                {/if}
              </div>
            </div>
            <span class="job-status">{job.status || (job.paused ? "paused" : "pending")}</span>
          </div>

          {#if jobPromptIsExpandable(job.prompt)}
            <details class="job-prompt-details">
              <summary class="job-prompt-summary">
                <span class="job-prompt-preview" aria-hidden="true">{job.prompt || ""}</span>
                <span class="job-prompt-toggle-label">
                  <span class="job-prompt-show">Show full prompt</span>
                  <span class="job-prompt-hide">Hide prompt</span>
                </span>
              </summary>
              <div class="job-row-prompt job-row-prompt-full">{job.prompt || ""}</div>
            </details>
          {:else}
            <div class="job-row-prompt">{job.prompt || ""}</div>
          {/if}

          <div class="job-row-actions">
            {#if !job.run_at_epoch}
              <button
                type="button"
                class="job-action"
                aria-label={`Edit ${job.name}`}
                disabled={saving}
                onclick={() => edit(job)}
              >
                Edit
              </button>
            {/if}
            <button
              type="button"
              class="job-action"
              aria-label={`${job.paused ? "Resume" : "Pause"} ${job.name}`}
              disabled={saving}
              onclick={() =>
                void command(
                  { action: job.paused ? "resume" : "pause", name: job.name },
                  `${job.paused ? "Resumed" : "Paused"} ${job.name}`,
                )}
            >
              {job.paused ? "Resume" : "Pause"}
            </button>
            <button
              type="button"
              class="job-action"
              aria-label={`Remove ${job.name}`}
              disabled={saving}
              onclick={() => requestRemove(job)}
            >
              Remove
            </button>
          </div>
        </article>
      {/each}
    </div>

    {#if pagination.pageCount > 1}
      <nav class="jobs-pagination" aria-label="Scheduled jobs pages">
        <button
          type="button"
          class="jobs-secondary-button"
          disabled={pagination.page === 1}
          onclick={() => (page = pagination.page - 1)}
        >
          Previous
        </button>
        <span class="jobs-pagination-status" aria-live="polite">
          Page {pagination.page} of {pagination.pageCount}
        </span>
        <button
          type="button"
          class="jobs-secondary-button"
          disabled={pagination.page === pagination.pageCount}
          onclick={() => (page = pagination.page + 1)}
        >
          Next
        </button>
      </nav>
    {/if}

    <form
      class="jobs-form"
      onsubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <h3>{editing ? `Edit ${editing}` : "Add job"}</h3>
      <label>
        <span>Name</span>
        <input id="jobName" name="name" bind:value={name} autocomplete="off" readonly={Boolean(editing)} required />
      </label>
      <label>
        <span>Prompt</span>
        <textarea id="jobPrompt" name="prompt" bind:value={prompt} rows="3" required></textarea>
      </label>
      <div class="jobs-form-grid">
        <label>
          <span>Schedule</span>
          <select id="jobSchedule" name="schedule" bind:value={schedule}>
            <option value="interval">Interval</option>
            <option value="daily">Daily</option>
          </select>
        </label>
        {#if schedule === "interval"}
          <label>
            <span>Every (minutes)</span>
            <input id="jobInterval" name="interval" bind:value={interval} type="number" min="0.1" step="0.1" />
          </label>
        {:else}
          <label>
            <span>At</span>
            <input id="jobDailyAt" name="dailyAt" bind:value={dailyAt} type="time" />
          </label>
        {/if}
      </div>

      {#if schedule === "interval"}
        <label class="jobs-check">
          <input id="jobExact" name="exact" bind:checked={exact} type="checkbox" />
          <span>Exact interval</span>
        </label>
      {/if}

      <div class="jobs-form-actions">
        <button type="button" class="jobs-secondary-button" disabled={saving} onclick={reset}>
          {editing ? "Cancel edit" : "Reset"}
        </button>
        <button type="submit" class="jobs-primary-button" disabled={saving}>Save job</button>
      </div>
    </form>

    <div class="jobs-page-footer">
      <button
        type="button"
        class="jobs-danger-button"
        disabled={!jobs.length || saving}
        onclick={requestClear}
      >
        Clear all jobs
      </button>
    </div>
  </div>

  <dialog
    {@attach dialogVisibility(() => Boolean(confirmation), () => true, cancelConfirmation)}
    class="jobs-confirm-dialog"
    aria-labelledby="jobsConfirmTitle"
    aria-describedby="jobsConfirmDescription"
    onclick={(event) => {
      if (event.target === event.currentTarget) cancelConfirmation();
    }}
  >
    <div class="jobs-confirm-shell">
      <h3 id="jobsConfirmTitle">
        {confirmation?.kind === "clear" ? "Clear scheduled jobs?" : "Remove scheduled job?"}
      </h3>
      <p id="jobsConfirmDescription">
        {#if confirmation?.kind === "clear"}
          This will remove all {confirmation.count} configured jobs. This cannot be undone.
        {:else if confirmation?.kind === "remove"}
          Remove “{confirmation.job.name}”? This cannot be undone.
        {/if}
      </p>
      <div class="jobs-confirm-actions">
        <button
          type="button"
          class="jobs-secondary-button"
          disabled={saving}
          onclick={cancelConfirmation}
        >
          Cancel
        </button>
        <button
          type="button"
          class="jobs-danger-button"
          disabled={saving}
          onclick={() => void confirmDestructiveAction()}
        >
          {confirmation?.kind === "clear" ? "Clear all jobs" : "Remove job"}
        </button>
      </div>
    </div>
  </dialog>
</section>
