<script lang="ts">
  import { MediaQuery } from "svelte/reactivity";

  import { dialogVisibility } from "./browserAttachments.svelte";
  import { formatClockTime12Hour, formatDailyTime12Hour, postJsonRequest } from "./clientLogic";
  import { jobPromptIsExpandable } from "./jobs";
  import { registerJobsDialog } from "./uiControllers";

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

  const mobile = new MediaQuery("(max-width: 600px)");
  let dialogOpen = $state(false);
  let presentation = $state<"modal" | "stack">("modal");
  let jobs = $state.raw<Job[]>([]);
  let status = $state("");
  let saving = $state(false);
  let editing = $state("");
  let name = $state("");
  let prompt = $state("");
  let schedule = $state("interval");
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

  export async function show() {
    reset();
    presentation = mobile.current ? "stack" : "modal";
    dialogOpen = true;
    await load();
  }

  export function close() {
    dialogOpen = false;
  }

  registerJobsDialog({ open: show, close });
</script>

<dialog
  {@attach dialogVisibility(() => dialogOpen, () => presentation === "modal", close)}
  class="jobs-dialog"
  id="jobsDialog"
  aria-labelledby="jobsDialogTitle"
  data-presentation={presentation}
  onclick={(event) => {
    if (event.target === event.currentTarget && presentation !== "stack") close();
  }}
>
  <div class="jobs-dialog-shell">
    <header class="jobs-dialog-header">
      <div class="chat-heading">
        <div class="heading-title" id="jobsDialogTitle">Scheduled jobs</div>
        <div class="heading-meta">Create and manage scheduled prompts.</div>
      </div>
      <button
        type="button"
        class="jobs-icon-button"
        aria-label="Close scheduled jobs"
        onclick={close}
      >
        ×
      </button>
    </header>

    <div class="jobs-dialog-status" role="status">{status}</div>

    <div class="jobs-list">
      {#if !jobs.length}<div class="jobs-empty">No scheduled jobs.</div>{/if}

      {#each jobs as job (job.name)}
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
              <button type="button" class="job-action" onclick={() => edit(job)}>Edit</button>
            {/if}
            <button
              type="button"
              class="job-action"
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
              onclick={() =>
                void command({ action: "remove", name: job.name }, `Removed ${job.name}`)}
            >
              Remove
            </button>
          </div>
        </article>
      {/each}
    </div>

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
        <input bind:value={name} autocomplete="off" readonly={Boolean(editing)} required />
      </label>
      <label>
        <span>Prompt</span>
        <textarea bind:value={prompt} rows="3" required></textarea>
      </label>
      <div class="jobs-form-grid">
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
            <input bind:value={interval} type="number" min="0.1" step="0.1" />
          </label>
        {:else}
          <label>
            <span>At</span>
            <input bind:value={dailyAt} type="time" />
          </label>
        {/if}
      </div>

      {#if schedule === "interval"}
        <label class="jobs-check">
          <input bind:checked={exact} type="checkbox" />
          <span>Exact interval</span>
        </label>
      {/if}

      <div class="jobs-form-actions">
        <button type="button" class="jobs-secondary-button" onclick={reset}>Reset</button>
        <button type="submit" class="jobs-primary-button" disabled={saving}>Save job</button>
      </div>
    </form>

    <div class="jobs-dialog-footer">
      <button
        type="button"
        class="jobs-danger-button"
        disabled={!jobs.length || saving}
        onclick={() => {
          if (confirm(`Clear all ${jobs.length} scheduled jobs?`)) {
            void command({ action: "clear" }, "Cleared all scheduled jobs");
          }
        }}
      >
        Clear all jobs
      </button>
    </div>
  </div>
</dialog>
