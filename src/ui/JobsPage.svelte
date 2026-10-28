<script lang="ts">
  import { onMount, tick } from "svelte";
  import { isLongJob, sortJobs } from "./jobSorting";

  type ImageRef = { ref: string; name: string; url: string };

  type Job = {
    images: ImageRef[];
    name: string;
    created_order: number;
    prompt: string;
    status: string;
    status_message: string;
    paused: boolean;
    run_at_epoch: number | null;
    pin_chat: boolean;
    daily_at: string | null;
    interval_minutes: number;
    exact_interval: boolean;
    source_revision: string;
    next_due_at_epoch: number;
    last_sent_at: number;
    last_uncertain_send_at: number;
  };

  type JobFilter = "pending" | "healthy" | "paused" | "unhealthy";
  const filterOptions: { key: JobFilter; label: string; title: string }[] = [
    { key: "pending", label: "Pending", title: "Pending or queued jobs" },
    { key: "healthy", label: "Healthy", title: "Jobs whose last dispatch succeeded" },
    { key: "paused", label: "Paused", title: "Paused jobs" },
    { key: "unhealthy", label: "Unhealthy", title: "Failing, rate-limited, or unconfirmed jobs" },
  ];

  type EditorRoute = { kind: "new"; once?: boolean } | { kind: "edit"; name: string };

  const pageSize = 10;
  const refreshIntervalMs = 5000;
  let jobs = $state<Job[]>([]);
  let activeFilters = $state<Record<JobFilter, boolean>>({
    pending: true,
    healthy: true,
    paused: true,
    unhealthy: true,
  });
  let showLongJobs = $state(true);
  let longJobsCount = $derived(jobs.filter(isLongJob).length);
  let cadenceJobs = $derived(jobs.filter((job) => showLongJobs || !isLongJob(job)));
  let filteredJobs = $derived(cadenceJobs.filter((job) => activeFilters[jobFilter(job)]));
  let filterCounts = $derived(
    cadenceJobs.reduce<Record<JobFilter, number>>(
      (counts, job) => {
        counts[jobFilter(job)] += 1;
        return counts;
      },
      { pending: 0, healthy: 0, paused: 0, unhealthy: 0 },
    ),
  );
  let page = $state(1);
  let pageCount = $derived(Math.max(1, Math.ceil(filteredJobs.length / pageSize)));
  let pageStart = $derived((page - 1) * pageSize);
  let pageEnd = $derived(Math.min(pageStart + pageSize, filteredJobs.length));
  let visibleJobs = $derived(filteredJobs.slice(pageStart, pageEnd));
  let allVisiblePaused = $derived(visibleJobs.length > 0 && visibleJobs.every((job) => job.paused));
  let status = $state("");
  let saving = $state(false);
  let editing = $state("");
  let name = $state("");
  let prompt = $state("");
  let images = $state<ImageRef[]>([]);
  let uploadingImage = $state(false);
  let imageInput: HTMLInputElement;
  let schedule = $state<"interval" | "daily" | "once">("once");
  let interval = $state("40");
  let onceDelay = $state("0");
  let pinChat = $state(false);
  let initialOnceDelay = "0";
  let originalRunAtEpoch: number | null = null;
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
  let runOnce = $derived(!editing && schedule === "once");
  let duplicateName = $derived(!runOnce && !editing && jobs.some((job) => job.name === name.trim()));
  let promptCharacters = $derived(prompt.length);
  let promptLines = $derived(prompt ? prompt.split("\n").length : 0);
  let loadInFlight = false;
  let dataGeneration = 0;

  function reset() {
    editing = "";
    name = "";
    prompt = "";
    images = [];
    schedule = "once";
    interval = "40";
    onceDelay = "0";
    pinChat = false;
    initialOnceDelay = "0";
    originalRunAtEpoch = null;
    dailyAt = "09:00";
    exact = false;
  }

  function formSnapshot() {
    return JSON.stringify({ name, prompt, images: images.map((image) => image.ref), schedule, interval, onceDelay, pinChat, dailyAt, exact });
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
    if (url.searchParams.has("new")) return { kind: "new", once: url.searchParams.get("new") === "once" };
    const jobName = url.searchParams.get("edit");
    return jobName === null ? null : { kind: "edit", name: jobName };
  }

  function routeKey(route: EditorRoute | null) {
    return route?.kind === "new" ? (route.once ? "new:once" : "new") : route?.kind === "edit" ? "edit:" + route.name : "";
  }

  function jobsUrl() {
    const url = new URL(window.location.href);
    url.searchParams.delete("new");
    url.searchParams.delete("edit");
    return url;
  }

  function workspaceScroll() {
    return document.querySelector<HTMLElement>(".jobs-workspace");
  }

  function restoreListScroll() {
    const pane = workspaceScroll();
    if (pane) pane.scrollTop = listScrollY;
    else window.scrollTo(0, listScrollY);
  }

  function keepFocusedPromptVisible() {
    if (!editorOpen || !window.matchMedia("(max-width: 680px)").matches) return;
    const pane = workspaceScroll();
    const focused = document.activeElement;
    if (!pane || !(focused instanceof HTMLTextAreaElement) || !editorPage?.contains(focused)) return;
    const footerTop = editorPage.querySelector<HTMLElement>(".editor-footer")?.getBoundingClientRect().top ?? innerHeight;
    const visibleBottom = Math.min(footerTop, window.visualViewport?.height ?? innerHeight) - 44;
    const overlap = focused.getBoundingClientRect().bottom - visibleBottom;
    if (overlap > 0) pane.scrollTop += overlap;
  }

  function leaveEditor() {
    if (window.history.state?.promptaEditor === true) {
      window.history.back();
    } else {
      window.history.replaceState(null, "", jobsUrl());
      closeEditorState();
      requestAnimationFrame(restoreListScroll);
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
      const pane = workspaceScroll();
      if (pane) pane.scrollTop = 0;
      else window.scrollTo(0, 0);
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
      if (route.once) schedule = "once";
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
      images = [...(job.images || [])];
      schedule = job.run_at_epoch ? "once" : job.daily_at ? "daily" : "interval";
      originalRunAtEpoch = job.run_at_epoch;
      pinChat = job.pin_chat;
      onceDelay = String(job.run_at_epoch ? Math.max(0, Math.round((job.run_at_epoch - Date.now() / 1000) / 6) / 10) : 0);
      initialOnceDelay = onceDelay;
      dailyAt = job.daily_at || "09:00";
      interval = String(job.interval_minutes || 40);
      exact = job.exact_interval;
    }
    activeEditorRoute = routeKey(route);
    openEditor(route.kind === "new" && schedule !== "once");
  }

  function pushEditor(route: EditorRoute) {
    listScrollY = workspaceScroll()?.scrollTop ?? window.scrollY;
    const url = jobsUrl();
    if (route.kind === "new") url.searchParams.set("new", route.once ? "once" : "1");
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
      requestAnimationFrame(restoreListScroll);
    }
  }

  function beginNew() {
    pushEditor({ kind: "new" });
  }

  function beginOnce() {
    pushEditor({ kind: "new", once: true });
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

  function jobFilter(job: Job): JobFilter {
    if (job.paused) return "paused";
    if (
      job.last_uncertain_send_at > job.last_sent_at ||
      job.status === "failing" ||
      job.status === "rate-limited"
    ) return "unhealthy";
    if (job.status === "healthy") return "healthy";
    return "pending";
  }

  function toggleFilter(filter: JobFilter) {
    activeFilters = { ...activeFilters, [filter]: !activeFilters[filter] };
    page = 1;
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
      JSON.stringify(left.images) === JSON.stringify(right.images) &&
      left.status === right.status &&
      left.status_message === right.status_message &&
      left.paused === right.paused &&
      left.run_at_epoch === right.run_at_epoch &&
      left.pin_chat === right.pin_chat &&
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
    page = Math.max(1, Math.min(page, pageCount));
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
    status = payload.action === "fire_now" || payload.action === "run_once" ? "Queuing fresh chat…" : "Saving…";

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

  async function addImages(input: HTMLInputElement) {
    const files = Array.from(input.files || []);
    input.value = "";
    if (!files.length || uploadingImage) return;
    if (images.length + files.length > 4) {
      editorError = "At most four images per job.";
      return;
    }
    const route = activeEditorRoute;
    uploadingImage = true;
    editorError = "";
    try {
      for (const file of files) {
        if (file.size > 8 * 1024 * 1024) throw new Error("Images must be 8 MiB or smaller.");
        const data = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onerror = () => reject(new Error("Could not read image."));
          reader.onload = () => {
            const value = reader.result;
            if (typeof value !== "string" || !value.includes(",")) reject(new Error("Could not encode image."));
            else resolve(value.split(",", 2)[1]);
          };
          reader.readAsDataURL(file);
        });
        const response = await fetch("./api/images", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ name: file.name, data }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(String(result.error || "Image upload failed."));
        if (activeEditorRoute !== route) return;
        images = [...images, result.image as ImageRef];
        await tick();
        editorPage?.querySelector(".job-image-preview:last-child")?.scrollIntoView({
          block: "nearest",
          behavior: "smooth",
        });
      }
    } catch (error) {
      if (activeEditorRoute === route) editorError = String(error).replace(/^Error:\s*/, "");
    } finally {
      uploadingImage = false;
    }
  }

  async function submit() {
    if (saving || uploadingImage || !dirty || duplicateName) return;
    editorError = "";
    const jobName = name.trim();
    const jobPrompt = prompt.trim();
    if (!jobPrompt || (!runOnce && !jobName)) return;

    if (runOnce) {
      const delayMinutes = Number(onceDelay);
      const queued = await command(
        { action: "run_once", prompt: jobPrompt, images: images.map((image) => image.ref), delay_minutes: delayMinutes, pin_chat: pinChat },
        delayMinutes ? `Scheduled once in ${delayMinutes} minutes (under Long jobs).` : "Queued one fresh chat.",
      );
      if (queued) {
        initialForm = formSnapshot();
        leaveEditor();
      } else editorError = status;
      return;
    }
    const daily = schedule === "daily";
    const saved = await command(
      {
        action: "add",
        name: jobName,
        prompt: jobPrompt,
        images: images.map((image) => image.ref),
        schedule,
        pin_chat: schedule === "once" && pinChat,
        daily_at: daily ? dailyAt : "",
        interval_minutes: schedule === "interval" ? Number(interval) : null,
        exact_interval: schedule === "interval" && exact,
        ...(schedule === "once" && (!originalRunAtEpoch || onceDelay !== initialOnceDelay)
          ? { delay_minutes: Number(onceDelay) }
          : {}),
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

  async function toggleVisible() {
    const names = visibleJobs.map((job) => job.name);
    if (!names.length) return;
    const action = allVisiblePaused ? "resume_many" : "pause_many";
    const success = allVisiblePaused ? "Resumed visible jobs." : "Paused visible jobs.";
    await command({ action, names }, success);
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
    const onViewportResize = () => requestAnimationFrame(keepFocusedPromptVisible);
    window.addEventListener("resize", onViewportResize);
    window.visualViewport?.addEventListener("resize", onViewportResize);
    void load().then(syncEditorFromUrl);
    window.addEventListener("popstate", syncEditorFromUrl);
    const timer = window.setInterval(() => {
      void load({ quiet: true });
    }, refreshIntervalMs);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("beforeunload", onBeforeUnload);
      window.removeEventListener("resize", onViewportResize);
      window.visualViewport?.removeEventListener("resize", onViewportResize);
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
      <span>{cadenceJobs.length}</span>
    </div>

    <div class="toolbar-actions">
      <span class="status-line" role="status" aria-live="polite">{status}</span>

      <button
        class="toolbar-button visible-toggle"
        type="button"
        disabled={!visibleJobs.length || saving}
        title={allVisiblePaused ? "Resume the jobs shown on this page" : "Pause the jobs shown on this page"}
        onclick={() => void toggleVisible()}
      >{allVisiblePaused ? "Resume visible" : "Pause visible"} ({visibleJobs.length})</button>

      <button class="toolbar-button refresh-action" type="button" disabled={saving} onclick={() => void load()}>Refresh</button>
      <button class="toolbar-button run-once-action" type="button" disabled={saving} onclick={beginOnce}>Run once</button>
      <button class="primary-button" type="button" disabled={saving} onclick={beginNew}>New job</button>
    </div>
  </div>

  <div class="jobs-summary" role="group" aria-label="Filter jobs">
    {#each filterOptions as option (option.key)}
      <button
        class:chosen={activeFilters[option.key]}
        class="filter-chip"
        type="button"
        aria-pressed={activeFilters[option.key]}
        title={option.title}
        onclick={() => toggleFilter(option.key)}
      >{option.label} <span>{filterCounts[option.key]}</span></button>
    {/each}
    <button
      class:chosen={showLongJobs}
      class="filter-chip"
      type="button"
      aria-pressed={showLongJobs}
      title="Include jobs running less often than daily and scheduled one-time jobs"
      onclick={() => { showLongJobs = !showLongJobs; page = 1; }}
    >Long jobs <span>{longJobsCount}</span></button>
  </div>

  <div class="jobs-table" role="table" aria-label="Scheduled jobs">
    <div class="jobs-table-head" role="row">
      <span role="columnheader">Job</span>
      <span role="columnheader">Schedule</span>
      <span role="columnheader">Next run</span>
      <span role="columnheader">State</span>
      <span role="columnheader" class="actions-heading">Actions</span>
    </div>

    {#if filteredJobs.length === 0}
      <div class="empty-row">{jobs.length ? "No jobs match these filters." : "No scheduled jobs."}</div>
    {/if}

    {#each visibleJobs as job (job.name)}
      <div class="job-row" role="row">
        <div class="job-main" role="cell">
          <div class="job-name">{job.name}</div>
          <div class="job-prompt" title={job.prompt}>{job.prompt}</div>
          {#if job.images?.length}<div class="job-image-count">{job.images.length} image{job.images.length === 1 ? "" : "s"}</div>{/if}
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

  {#if filteredJobs.length > pageSize}
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
          <button class="toolbar-button editor-back" type="button" disabled={saving} onclick={requestClose}>
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="m12 19-7-7 7-7" />
              <path d="M5 12h14" />
            </svg>
            Jobs
          </button>
          <div class="editor-title">
            <h2 id="editor-title">{editing ? "Edit job" : runOnce ? "Run once" : "New job"}</h2>
            {#if editing}<span title={editing}>{editing}</span>{/if}
          </div>
        </div>

        <div class={"editor-body" + (images.length ? " has-images" : "")}>
          <div class="editor-settings">
            {#if !runOnce}
              <label class="name-field">
                <span>Name</span>
                <input bind:value={name} autocomplete="off" readonly={Boolean(editing)} required />
              </label>
            {/if}

            <label>
              <span>Schedule</span>
              <select bind:value={schedule}>
                <option value="interval">Interval</option>
                <option value="daily">Daily</option>
                <option value="once">Once</option>
              </select>
            </label>

            {#if schedule === "interval"}
              <label>
                <span>Every (minutes)</span>
                <input bind:value={interval} type="number" min="0.1" max="43200" step="0.1" required />
              </label>
            {:else if schedule === "once"}
              <label>
                <span>Delay (minutes, 0 = now)</span>
                <input bind:value={onceDelay} type="number" min="0" max="43200" step="0.1" required />
              </label>
            {:else if schedule === "daily"}
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
          {:else if schedule === "once"}
            <label class="checkbox-row">
              <input bind:checked={pinChat} type="checkbox" />
              <span>Pin chat</span>
            </label>
          {/if}

          <label class="prompt-field">
            <span>Prompt</span>
            <textarea bind:value={prompt} rows="14" required onfocus={() => requestAnimationFrame(keepFocusedPromptVisible)}></textarea>
          </label>
          <div class="prompt-counter">{promptCharacters.toLocaleString()} characters · {promptLines.toLocaleString()} lines</div>
          <div class="job-image-picker">
            <button class="toolbar-button" type="button" disabled={uploadingImage || saving || images.length >= 4} onclick={() => imageInput?.click()}>Add images</button>
            <input bind:this={imageInput} class="image-input" type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple disabled={uploadingImage || saving || images.length >= 4} onchange={(event) => void addImages(event.currentTarget)} />
            <span>{uploadingImage ? "Uploading…" : images.length + "/4 images"}</span>
          </div>
          {#if images.length}
            <div class="job-image-previews">
              {#each images as image (image.ref)}
                <div class="job-image-preview">
                  <img src={image.url} alt={image.name} />
                  <span title={image.name}>{image.name}</span>
                  <button type="button" title={"Remove " + image.name} aria-label={"Remove " + image.name} disabled={saving || uploadingImage} onclick={() => (images = images.filter((item) => item.ref !== image.ref))}>×</button>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <div class="editor-footer">
          <div class="editor-feedback" role={confirmDiscard ? "alertdialog" : "status"} aria-label={confirmDiscard ? "Discard unsaved changes" : undefined} aria-live="polite">
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
          {#if !confirmDiscard}
          <div class="editor-actions">
            <span class="keyboard-hint">Ctrl/⌘ + Enter to {runOnce ? "run" : "save"}</span>
            <button class="toolbar-button" type="button" disabled={saving} onclick={requestClose}>Cancel</button>
            <button class="primary-button" type="submit" disabled={saving || uploadingImage || !dirty || duplicateName || !prompt.trim() || (!runOnce && !name.trim())}>
              {saving ? (runOnce ? "Queuing…" : "Saving…") : editing ? "Save changes" : runOnce ? (Number(onceDelay) > 0 ? "Schedule once" : "Run once") : "Create job"}
            </button>
          </div>
          {/if}
        </div>
      </form>
  </section>
{/if}
