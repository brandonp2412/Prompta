import { signal, computed, batch } from "@preact/signals-react";
import { isRepeatingJob, sortJobs } from "./jobSorting";
import { subscribeLiveUpdates } from "./liveUpdates";
import { localGet } from "./localRead";
import { localPost, localUploadTimeoutMs } from "./localMutation";
import {
  acknowledgeFreshQueueRequest,
  findFreshQueueReceiptStatus,
  freshQueueRequest,
} from "./freshQueueReceipt";
export type Props = { workspace?: HTMLDivElement };
export function createJobsPageController(initialProps: Props) {
  const tick = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

  const workspace = signal(initialProps.workspace);

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

  type DeliveryHealth = {
    admission?: { blocked: boolean; kind: string; reason: string };
    recovery: {
      active_captures: number;
      stale_capture_leases: number;
      recoverable: number;
      ready_for_read_only_probe: number;
      missing_verified_identity: number;
      unresolved_reply_captures: number;
      recoverable_reply_captures: number;
      due_reply_recovery_probes: number;
      security_pause_seconds: number;
      global_pace_seconds: number;
      account_read_backoff_seconds: number;
    };
    ready: boolean;
    issues: string[];
    queue: {
      queued: number;
      running: number;
      retrying: number;
      rate_limited: number;
      dead_lettered: number;
      outcome_unknown: number;
      oldest_pending_age_seconds: number;
      next_retry_at_epoch?: number;
    };
  };
  let deliveryHealth = signal<DeliveryHealth | null>(null);
  let deliveryHealthError = signal("");
  let jobsLoadError = signal("");
  const pendingDeliveries = computed(() =>
    deliveryHealth.value
      ? deliveryHealth.value.queue.queued +
        deliveryHealth.value.queue.running +
        deliveryHealth.value.queue.retrying +
        deliveryHealth.value.queue.rate_limited
      : 0,
  );
  const recoveryPauseSeconds = computed(() =>
    deliveryHealth.value
      ? Math.max(
          deliveryHealth.value.recovery.account_read_backoff_seconds,
          deliveryHealth.value.recovery.security_pause_seconds,
        )
      : 0,
  );

  type QueueRequestContext = { prompt: string; images: string[]; scope: string };

  type JobFilter = "pending" | "healthy" | "paused" | "unhealthy";
  const filterOptions: { key: JobFilter; label: string; title: string }[] = [
    { key: "pending", label: "Pending", title: "Pending or queued jobs" },
    { key: "healthy", label: "Healthy", title: "Jobs whose last dispatch succeeded" },
    { key: "paused", label: "Paused", title: "Paused jobs" },
    { key: "unhealthy", label: "Unhealthy", title: "Failing, rate-limited, or unconfirmed jobs" },
  ];

  type EditorRoute = { kind: "new"; once?: boolean } | { kind: "edit"; name: string };

  const pageSize = 10;
  let jobs = signal<Job[]>([]);
  let activeFilters = signal<Record<JobFilter, boolean>>({
    pending: true,
    healthy: true,
    paused: true,
    unhealthy: true,
  });
  let showRepeatingJobs = signal(true);
  let repeatingJobsCount = computed(() => jobs.value.filter(isRepeatingJob).length);
  let cadenceJobs = computed(() =>
    jobs.value.filter((job) => showRepeatingJobs.value || !isRepeatingJob(job)),
  );
  let filteredJobs = computed(() =>
    cadenceJobs.value.filter((job) => activeFilters.value[jobFilter(job)]),
  );
  let filterCounts = computed(() =>
    cadenceJobs.value.reduce<Record<JobFilter, number>>(
      (counts, job) => {
        counts[jobFilter(job)] += 1;
        return counts;
      },
      { pending: 0, healthy: 0, paused: 0, unhealthy: 0 },
    ),
  );
  let page = signal(1);
  let pageCount = computed(() => Math.max(1, Math.ceil(filteredJobs.value.length / pageSize)));
  let pageStart = computed(() => (page.value - 1) * pageSize);
  let pageEnd = computed(() => Math.min(pageStart.value + pageSize, filteredJobs.value.length));
  let visibleJobs = computed(() => filteredJobs.value.slice(pageStart.value, pageEnd.value));
  let allVisiblePaused = computed(
    () => visibleJobs.value.length > 0 && visibleJobs.value.every((job) => job.paused),
  );
  let status = signal("");
  let saving = signal(false);
  let editing = signal("");
  let name = signal("");
  let prompt = signal("");
  let images = signal<ImageRef[]>([]);
  let uploadingImage = signal(false);
  let imageUploadGeneration = 0;
  let imageUploadAbort: AbortController | null = null;
  let imageInput = signal<HTMLInputElement>();
  let schedule = signal<"interval" | "daily" | "once">("once");
  let interval = signal("40");
  let onceDelay = signal("0");
  let pinChat = signal(false);
  let initialOnceDelay = "0";
  let originalRunAtEpoch: number | null = null;
  let dailyAt = signal("09:00");
  let exact = signal(false);
  let editorOpen = signal(false);
  let editorPage = signal<HTMLElement>();
  let editorFooter = signal<HTMLDivElement>();
  let nameInput = signal<HTMLInputElement>();
  let promptInput = signal<HTMLTextAreaElement>();
  let editorForm = signal<HTMLFormElement>();
  let jobsTitle = signal<HTMLHeadingElement>();
  let imagePreviewList = signal<HTMLDivElement>();
  let activeEditorRoute = signal("");
  let listScrollY = 0;
  let editorError = signal("");
  let confirmDiscard = signal(false);
  let initialForm = signal("");
  let dirty = computed(() => editorOpen.value && formSnapshot() !== initialForm.value);
  let runOnce = computed(() => !editing.value && activeEditorRoute.value === "new:once");
  let duplicateName = computed(
    () =>
      !runOnce.value && !editing.value && jobs.value.some((job) => job.name === name.value.trim()),
  );
  let loadInFlight = false;
  let refreshPending = false;
  let dataGeneration = 0;
  let healthInFlight = false;
  let healthRefreshPending = false;

  function reset() {
    editing.value = "";
    name.value = "";
    prompt.value = "";
    images.value = [];
    schedule.value = "interval";
    interval.value = "40";
    onceDelay.value = "0";
    pinChat.value = false;
    initialOnceDelay = "0";
    originalRunAtEpoch = null;
    dailyAt.value = "09:00";
    exact.value = false;
  }

  function formSnapshot() {
    return JSON.stringify({
      name: name.value,
      prompt: prompt.value,
      images: images.value.map((image) => image.ref),
      schedule: schedule.value,
      interval: interval.value,
      onceDelay: onceDelay.value,
      pinChat: pinChat.value,
      dailyAt: dailyAt.value,
      exact: exact.value,
    });
  }

  function cancelEditorUpload() {
    imageUploadGeneration += 1;
    imageUploadAbort?.abort();
    imageUploadAbort = null;
    uploadingImage.value = false;
  }

  function closeEditorState() {
    cancelEditorUpload();
    editorOpen.value = false;
    activeEditorRoute.value = "";
    confirmDiscard.value = false;
    editorError.value = "";
    reset();
  }

  function editorRouteFromUrl(): EditorRoute | null {
    const url = new URL(window.location.href);
    if (url.searchParams.has("new"))
      return { kind: "new", once: url.searchParams.get("new") === "once" };
    const jobName = url.searchParams.get("edit");
    return jobName === null ? null : { kind: "edit", name: jobName };
  }

  function routeKey(route: EditorRoute | null) {
    return route?.kind === "new"
      ? route.once
        ? "new:once"
        : "new"
      : route?.kind === "edit"
        ? "edit:" + route.name
        : "";
  }

  function jobsUrl() {
    const url = new URL(window.location.href);
    url.searchParams.delete("new");
    url.searchParams.delete("edit");
    return url;
  }

  function workspaceScroll() {
    return workspace.value;
  }

  function restoreListScroll() {
    const pane = workspaceScroll();
    if (pane) pane.scrollTop = listScrollY;
    else window.scrollTo(0, listScrollY);
  }

  function keepFocusedPromptVisible() {
    if (!editorOpen.value || !window.matchMedia("(max-width: 680px)").matches) return;
    const pane = workspaceScroll();
    const focused = document.activeElement;
    if (!pane || !(focused instanceof HTMLTextAreaElement) || !editorPage.value?.contains(focused))
      return;
    const footerTop = editorFooter.value?.getBoundingClientRect().top ?? innerHeight;
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
    if (saving.value) return;
    if (dirty.value) {
      confirmDiscard.value = true;
      return;
    }
    leaveEditor();
  }

  function discardEditor() {
    initialForm.value = formSnapshot();
    leaveEditor();
  }

  function openEditor(focusName: boolean) {
    editorError.value = "";
    confirmDiscard.value = false;
    initialForm.value = formSnapshot();
    editorOpen.value = true;
    requestAnimationFrame(() => {
      const pane = workspaceScroll();
      if (pane) pane.scrollTop = 0;
      else window.scrollTo(0, 0);
      if (focusName) {
        nameInput.value?.focus();
      } else if (window.matchMedia("(pointer: coarse)").matches) {
        editorPage.value?.focus();
      } else {
        const textarea = promptInput.value;
        textarea?.focus();
        textarea?.setSelectionRange(0, 0);
      }
    });
  }

  function showEditor(route: EditorRoute) {
    cancelEditorUpload();
    if (route.kind === "new") {
      reset();
      if (route.once) schedule.value = "once";
    } else {
      const job = jobs.value.find((item) => item.name === route.name);
      if (!job) {
        status.value = "Job not found: " + route.name;
        window.history.replaceState(null, "", jobsUrl());
        closeEditorState();
        return;
      }
      editing.value = job.name;
      name.value = job.name;
      prompt.value = job.prompt;
      images.value = [...(job.images || [])];
      schedule.value = job.run_at_epoch ? "once" : job.daily_at ? "daily" : "interval";
      originalRunAtEpoch = job.run_at_epoch;
      pinChat.value = job.pin_chat;
      onceDelay.value = String(
        job.run_at_epoch
          ? Math.max(0, Math.round((job.run_at_epoch - Date.now() / 1000) / 6) / 10)
          : 0,
      );
      initialOnceDelay = onceDelay.value;
      dailyAt.value = job.daily_at || "09:00";
      interval.value = String(job.interval_minutes || 40);
      exact.value = job.exact_interval;
    }
    activeEditorRoute.value = routeKey(route);
    openEditor(route.kind === "new" && schedule.value !== "once");
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
    if (routeKey(route) === activeEditorRoute.value) return;
    if (saving.value || (dirty.value && !window.confirm("Discard unsaved job changes?"))) {
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
    if (!editorOpen.value || saving.value) return;
    if (event.key === "Escape") {
      event.preventDefault();
      requestClose();
      return;
    }
    if (!dirty.value || duplicateName.value) return;
    if (!(event.ctrlKey || event.metaKey) || event.key !== "Enter") return;
    if (!(event.target instanceof Node) || !editorPage.value?.contains(event.target)) return;
    event.preventDefault();
    editorForm.value?.requestSubmit();
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
    )
      return "unhealthy";
    if (job.status === "healthy") return "healthy";
    return "pending";
  }

  function toggleFilter(filter: JobFilter) {
    activeFilters.value = { ...activeFilters.value, [filter]: !activeFilters.value[filter] };
    page.value = 1;
  }

  function jobStateText(job: Job) {
    if (job.paused) return "paused";
    if (
      job.last_uncertain_send_at > job.last_sent_at ||
      (job.status === "failing" &&
        /lost send confirmation after dispatch/i.test(job.status_message))
    )
      return "unconfirmed";
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
    const unchanged =
      jobs.value.length === sortedJobs.length &&
      jobs.value.every((job, index) => sameJob(job, sortedJobs[index]));
    if (unchanged) return;

    jobs.value = sortedJobs;
    clampPage();
  }

  function clampPage() {
    page.value = Math.max(1, Math.min(page.value, pageCount.value));
  }

  function changePage(nextPage: number) {
    page.value = Math.max(1, Math.min(nextPage, pageCount.value));
    jobsTitle.value?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function loadDeliveryHealth() {
    if (healthInFlight) {
      healthRefreshPending = true;
      return;
    }
    healthInFlight = true;
    try {
      const response = await localGet("./api/health");
      if (!response.ok) throw new Error("Health unavailable");
      deliveryHealth.value = (await response.json()) as DeliveryHealth;
      deliveryHealthError.value = "";
    } catch {
      // Retain the last good snapshot and make the stale state explicit.
      deliveryHealthError.value =
        "Delivery health is temporarily unavailable; showing the last confirmed status.";
    } finally {
      healthInFlight = false;
      if (healthRefreshPending) {
        healthRefreshPending = false;
        void loadDeliveryHealth();
      }
    }
  }

  async function load({ quiet = false }: { quiet?: boolean } = {}) {
    if (quiet && document.visibilityState !== "visible") return;
    if (loadInFlight) {
      refreshPending = true;
      return;
    }

    loadInFlight = true;
    const requestGeneration = dataGeneration;
    if (!quiet) status.value = "Loading jobs…";

    try {
      const response = await localGet("./api/jobs");
      if (!response.ok) throw new Error(String(response.status) + " " + response.statusText);

      const result = await response.json();
      if (requestGeneration !== dataGeneration) return;

      const nextJobs: Job[] = Array.isArray(result.jobs) ? result.jobs : [];
      applyJobs(nextJobs);
      jobsLoadError.value = "";
      if (!quiet)
        status.value =
          String(jobs.value.length) +
          " configured job" +
          (jobs.value.length === 1 ? "" : "s") +
          ".";
    } catch (error) {
      if (requestGeneration === dataGeneration) {
        jobsLoadError.value = "Jobs could not be refreshed. The list may be out of date.";
        if (!quiet)
          status.value = "Could not load jobs: " + String(error).replace(/^Error:\s*/, "");
      }
    } finally {
      loadInFlight = false;
      if (refreshPending) {
        refreshPending = false;
        void load({ quiet: true });
      }
    }
  }

  async function command(
    payload: Record<string, unknown>,
    success: string,
    queueContext?: QueueRequestContext,
  ) {
    if (saving.value) return false;
    saving.value = true;
    dataGeneration += 1;
    status.value = queueContext ? "Queuing fresh chat…" : "Saving…";
    let request: Awaited<ReturnType<typeof freshQueueRequest>> | undefined;
    let definitivelyRejected = false;

    const reconcile = async (): Promise<"confirmed" | "terminal" | "missing"> => {
      if (!request) return "missing";
      const receipt = await findFreshQueueReceiptStatus(request.requestId);
      if (!receipt) return "missing";
      if (["outcome_unknown", "cancelled", "dead_lettered"].includes(receipt.status)) {
        // Existing terminal receipts must never be represented as a fresh success.
        status.value =
          receipt.status === "outcome_unknown"
            ? "The earlier run may have reached ChatGPT. No automatic resend was attempted."
            : "The earlier run ended without confirmed delivery. Review Chats before retrying.";
        await load({ quiet: true });
        return "terminal";
      }
      if (
        !["queued", "running", "retrying", "rate_limited", "succeeded"].includes(receipt.status)
      ) {
        status.value = "The saved queue receipt has an unknown state. No resend was attempted.";
        return "terminal";
      }
      acknowledgeFreshQueueRequest(request.fingerprint, request.requestId);
      await load({ quiet: true });
      status.value = success;
      return "confirmed";
    };
    try {
      if (queueContext) {
        request = await freshQueueRequest(
          queueContext.prompt,
          queueContext.images,
          queueContext.scope,
        );
        if (request.reused) {
          const previous = await reconcile();
          if (previous !== "missing") return previous === "confirmed";
        }
        payload = { ...payload, request_id: request.requestId };
      }
      const response = await localPost("./api/jobs", payload);
      definitivelyRejected = !response.ok && response.status < 500;
      const result = await response.json();
      if (!response.ok) {
        throw new Error(
          String(result.error || String(response.status) + " " + response.statusText),
        );
      }
      if (request) acknowledgeFreshQueueRequest(request.fingerprint, request.requestId);
      const nextJobs: Job[] = Array.isArray(result.jobs) ? result.jobs : [];
      applyJobs(nextJobs);
      status.value = success;
      return true;
    } catch (error) {
      if (request && !definitivelyRejected) {
        const recovered = await reconcile();
        if (recovered !== "missing") return recovered === "confirmed";
        status.value =
          "Queue receipt uncertain. The request ID is saved; press the same action again to reconcile safely.";
      } else {
        status.value = definitivelyRejected
          ? "Job update failed: " + String(error).replace(/^Error:\s*/, "")
          : "Job update could not be confirmed. Refresh Jobs before repeating the action.";
      }
      return false;
    } finally {
      saving.value = false;
    }
  }

  async function addImages(input: HTMLInputElement) {
    const files = Array.from(input.files || []);
    input.value = "";
    if (!files.length || uploadingImage.value) return;
    if (images.value.length + files.length > 4) {
      editorError.value = "At most four images per job.";
      return;
    }
    // Reject the entire batch before uploading anything, so selection errors
    // cannot leave a surprising subset of new attachments.
    if (
      files.some(
        (file) => !["image/png", "image/jpeg", "image/gif", "image/webp"].includes(file.type),
      )
    ) {
      editorError.value = "Only PNG, JPEG, GIF or WebP images are supported.";
      return;
    }
    if (files.some((file) => file.size > 8 * 1024 * 1024)) {
      editorError.value = "Images must be 8 MiB or smaller.";
      return;
    }
    const route = activeEditorRoute.value;
    const generation = ++imageUploadGeneration;
    const controller = new AbortController();
    imageUploadAbort = controller;
    const originalImages = [...images.value];
    uploadingImage.value = true;
    editorError.value = "";
    try {
      for (const file of files) {
        const data = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onerror = () => reject(new Error("Could not read image."));
          reader.onload = () => {
            const value = reader.result;
            if (typeof value !== "string" || !value.includes(","))
              reject(new Error("Could not encode image."));
            else resolve(value.split(",", 2)[1]);
          };
          reader.readAsDataURL(file);
        });
        if (generation !== imageUploadGeneration || activeEditorRoute.value !== route) return;
        const response = await localPost(
          "./api/images",
          { name: file.name, data },
          {
            timeoutMs: localUploadTimeoutMs,
            signal: controller.signal,
          },
        );
        if (generation !== imageUploadGeneration || activeEditorRoute.value !== route) return;
        if (!response.ok) throw new Error("Image upload failed.");
        const result = (await response.json()) as { image?: ImageRef };
        if (!result.image?.ref || !result.image.url.startsWith("./api/images/")) {
          throw new Error("Image upload receipt was invalid.");
        }
        if (images.value.some((image) => image.ref === result.image?.ref)) continue;
        images.value = [...images.value, result.image];
        await tick();
        if (generation !== imageUploadGeneration || activeEditorRoute.value !== route) return;
        imagePreviewList.value?.scrollIntoView({
          block: "nearest",
          behavior: "smooth",
        });
      }
    } catch (error) {
      if (generation === imageUploadGeneration && activeEditorRoute.value === route) {
        images.value = originalImages;
        editorError.value =
          error instanceof DOMException && error.name === "TimeoutError"
            ? "Image upload timed out. No new attachments were added; try again."
            : String(error).replace(/^Error:\s*/, "");
      }
    } finally {
      if (generation === imageUploadGeneration && activeEditorRoute.value === route) {
        imageUploadAbort = null;
        uploadingImage.value = false;
      }
    }
  }

  async function submit() {
    if (saving.value || uploadingImage.value || !dirty.value || duplicateName.value) return;
    editorError.value = "";
    const jobName = name.value.trim();
    const jobPrompt = prompt.value.trim();
    if (!jobPrompt || (!runOnce.value && !jobName)) return;

    if (runOnce.value) {
      const delayMinutes = Number(onceDelay.value);
      const refs = images.value.map((image) => image.ref);
      const queued = await command(
        {
          action: "run_once",
          prompt: jobPrompt,
          images: refs,
          delay_minutes: delayMinutes,
          pin_chat: pinChat.value,
        },
        delayMinutes ? `Scheduled once in ${delayMinutes} minutes.` : "Queued one fresh chat.",
        delayMinutes === 0
          ? { prompt: jobPrompt, images: refs, scope: "jobs:run-once:" + pinChat.value }
          : undefined,
      );
      if (queued) {
        initialForm.value = formSnapshot();
        leaveEditor();
      } else editorError.value = status.value;
      return;
    }
    const daily = schedule.value === "daily";
    const saved = await command(
      {
        action: "add",
        name: jobName,
        prompt: jobPrompt,
        images: images.value.map((image) => image.ref),
        schedule: schedule.value,
        pin_chat: schedule.value === "once" && pinChat.value,
        daily_at: daily ? dailyAt.value : "",
        interval_minutes: schedule.value === "interval" ? Number(interval.value) : null,
        exact_interval: schedule.value === "interval" && exact.value,
        ...(schedule.value === "once" &&
        (!originalRunAtEpoch || onceDelay.value !== initialOnceDelay)
          ? { delay_minutes: Number(onceDelay.value) }
          : {}),
      },
      "Saved " + jobName + ".",
    );
    if (saved) {
      initialForm.value = formSnapshot();
      leaveEditor();
    } else editorError.value = status.value;
  }

  function edit(job: Job) {
    pushEditor({ kind: "edit", name: job.name });
  }

  async function remove(job: Job) {
    if (!window.confirm("Remove “" + job.name + "”?")) return;
    const removed = await command(
      { action: "remove", name: job.name },
      "Removed " + job.name + ".",
    );
    if (removed && editing.value === job.name) leaveEditor();
  }

  async function toggleVisible() {
    const names = visibleJobs.value.map((job) => job.name);
    if (!names.length) return;
    const action = allVisiblePaused.value ? "resume_many" : "pause_many";
    const success = allVisiblePaused.value ? "Resumed visible jobs." : "Paused visible jobs.";
    await command({ action, names }, success);
  }

  async function clearAll() {
    if (
      !jobs.value.length ||
      !window.confirm("Remove all " + String(jobs.value.length) + " configured jobs?")
    )
      return;
    if ((await command({ action: "clear" }, "Cleared all scheduled jobs.")) && editorOpen.value)
      leaveEditor();
  }

  const onMountImpl = () => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty.value) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    const onViewportResize = () => requestAnimationFrame(keepFocusedPromptVisible);
    window.addEventListener("resize", onViewportResize);
    window.visualViewport?.addEventListener("resize", onViewportResize);
    void load().then(syncEditorFromUrl);
    void loadDeliveryHealth();
    const healthTimer = setInterval(() => {
      if (document.visibilityState === "visible") void loadDeliveryHealth();
    }, 30000);
    window.addEventListener("popstate", syncEditorFromUrl);
    const unsubscribe = subscribeLiveUpdates("jobs", () => {
      void load({ quiet: true });
      void loadDeliveryHealth();
    });
    return () => {
      clearInterval(healthTimer);
      unsubscribe();
      window.removeEventListener("beforeunload", onBeforeUnload);
      window.removeEventListener("resize", onViewportResize);
      window.visualViewport?.removeEventListener("resize", onViewportResize);
      window.removeEventListener("popstate", syncEditorFromUrl);
    };
  };
  function mount() {
    const cleanup = onMountImpl();
    const disposers: Array<() => void> = [];
    return () => {
      for (const dispose of disposers) dispose();
      if (typeof cleanup === "function") cleanup();
    };
  }
  function syncProps(next: Props) {
    batch(() => {
      if (workspace.peek() !== next.workspace) workspace.value = next.workspace;
    });
  }
  return {
    workspace,
    deliveryHealth,
    deliveryHealthError,
    jobsLoadError,
    pendingDeliveries,
    recoveryPauseSeconds,
    filterOptions,
    pageSize,
    jobs,
    activeFilters,
    showRepeatingJobs,
    repeatingJobsCount,
    cadenceJobs,
    filteredJobs,
    filterCounts,
    page,
    pageCount,
    pageStart,
    pageEnd,
    visibleJobs,
    allVisiblePaused,
    status,
    saving,
    editing,
    name,
    prompt,
    images,
    uploadingImage,
    imageUploadGeneration,
    imageUploadAbort,
    imageInput,
    schedule,
    interval,
    onceDelay,
    pinChat,
    initialOnceDelay,
    originalRunAtEpoch,
    dailyAt,
    exact,
    editorOpen,
    editorPage,
    editorFooter,
    nameInput,
    promptInput,
    editorForm,
    jobsTitle,
    imagePreviewList,
    activeEditorRoute,
    listScrollY,
    editorError,
    confirmDiscard,
    initialForm,
    dirty,
    runOnce,
    duplicateName,
    loadInFlight,
    refreshPending,
    dataGeneration,
    healthInFlight,
    healthRefreshPending,
    reset,
    formSnapshot,
    cancelEditorUpload,
    closeEditorState,
    editorRouteFromUrl,
    routeKey,
    jobsUrl,
    workspaceScroll,
    restoreListScroll,
    keepFocusedPromptVisible,
    leaveEditor,
    requestClose,
    discardEditor,
    openEditor,
    showEditor,
    pushEditor,
    syncEditorFromUrl,
    beginNew,
    beginOnce,
    onEditorKeydown,
    formatDate,
    scheduleText,
    jobFilter,
    toggleFilter,
    jobStateText,
    sameJob,
    applyJobs,
    clampPage,
    changePage,
    loadDeliveryHealth,
    load,
    command,
    addImages,
    submit,
    edit,
    remove,
    toggleVisible,
    clearAll,
    mount,
    syncProps,
  };
}
