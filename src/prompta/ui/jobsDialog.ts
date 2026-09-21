import { postJsonRequest as postJson } from "./clientLogic";

function requiredElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing required jobs UI element: ${selector}`);
  return element;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setTextIfChanged(element: Element, value) {
  const text = String(value ?? "");
  if (element.textContent !== text) element.textContent = text;
}

async function fetchJson(url, timeoutMs = 10_000) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return await response.json();
  } finally {
    window.clearTimeout(timeout);
  }
}

function formatJobMinutes(value) {
  const minutes = Number(value);
  if (!Number.isFinite(minutes)) return "";
  if (minutes >= 60 && minutes % 60 === 0) {
    const hours = minutes / 60;
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}

function jobScheduleText(job) {
  if (job.run_at_epoch) {
    const date = new Date(Number(job.run_at_epoch) * 1000);
    return `once · ${date.toLocaleString([], {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })}`;
  }
  if (job.daily_at) return `daily · ${job.daily_at}`;
  return `every ${formatJobMinutes(job.interval_minutes)}${job.exact_interval ? " · exact" : ""}`;
}

export function createJobsDialog({ closeSidebar, resizeComposer, syncSendButton }) {
  const els = {
    jobsSidebarButton: requiredElement<HTMLButtonElement>("#jobsSidebarButton"),
    jobsDialog: requiredElement<HTMLDialogElement>("#jobsDialog"),
    closeJobsDialog: requiredElement<HTMLButtonElement>("#closeJobsDialog"),
    jobsDialogStatus: requiredElement<HTMLElement>("#jobsDialogStatus"),
    jobsList: requiredElement<HTMLElement>("#jobsList"),
    jobsForm: requiredElement<HTMLFormElement>("#jobsForm"),
    jobsFormTitle: requiredElement<HTMLElement>("#jobsFormTitle"),
    jobNameInput: requiredElement<HTMLInputElement>("#jobNameInput"),
    jobPromptInput: requiredElement<HTMLTextAreaElement>("#jobPromptInput"),
    jobScheduleType: requiredElement<HTMLSelectElement>("#jobScheduleType"),
    jobIntervalField: requiredElement<HTMLElement>("#jobIntervalField"),
    jobIntervalInput: requiredElement<HTMLInputElement>("#jobIntervalInput"),
    jobDailyField: requiredElement<HTMLElement>("#jobDailyField"),
    jobDailyInput: requiredElement<HTMLInputElement>("#jobDailyInput"),
    jobExactField: requiredElement<HTMLElement>("#jobExactField"),
    jobExactInput: requiredElement<HTMLInputElement>("#jobExactInput"),
    resetJobForm: requiredElement<HTMLButtonElement>("#resetJobForm"),
    saveJobButton: requiredElement<HTMLButtonElement>("#saveJobButton"),
    clearJobsButton: requiredElement<HTMLButtonElement>("#clearJobsButton"),
    messageInput: requiredElement<HTMLTextAreaElement>("#messageInput"),
    slashMenu: requiredElement<HTMLElement>("#slashMenu"),
  };
  let scheduledJobs = [];
  const mobileJobsScreen = window.matchMedia("(max-width: 600px)");
  const appShell = document.querySelector<HTMLElement>(".app-shell");

  function closeJobsView() {
    if (!els.jobsDialog.open) return;
    els.jobsDialog.close();
  }

  function resetJobForm() {
    els.jobsForm.reset();
    setTextIfChanged(els.jobsFormTitle, "Add job");
    els.jobNameInput.readOnly = false;
    els.jobScheduleType.value = "interval";
    els.jobIntervalInput.value = "30";
    els.jobDailyInput.value = "09:00";
    els.jobExactInput.checked = false;
    syncJobScheduleFields();
  }

  function syncJobScheduleFields() {
    const daily = els.jobScheduleType.value === "daily";
    els.jobIntervalField.hidden = daily;
    els.jobDailyField.hidden = !daily;
    els.jobExactField.hidden = daily;
  }

  function renderJobs(jobs) {
    scheduledJobs = Array.isArray(jobs) ? jobs : [];
    els.clearJobsButton.disabled = scheduledJobs.length === 0;
    if (!scheduledJobs.length) {
      els.jobsList.innerHTML = '<div class="jobs-empty">No scheduled jobs.</div>';
      return;
    }
    els.jobsList.innerHTML = scheduledJobs.map((job) => {
      const paused = Boolean(job.paused);
      const canEdit = !job.run_at_epoch;
      return `
        <article class="job-row" data-job-name="${escapeHtml(job.name)}">
          <div class="job-row-top">
            <div>
              <div class="job-row-name">${escapeHtml(job.name)}</div>
              <div class="job-row-meta">${escapeHtml(jobScheduleText(job))}</div>
            </div>
            <span class="job-status">${escapeHtml(job.status || (paused ? "paused" : "pending"))}</span>
          </div>
          <div class="job-row-prompt">${escapeHtml(job.prompt || "")}</div>
          <div class="job-row-actions">
            ${canEdit ? '<button type="button" class="job-action" data-job-action="edit">Edit</button>' : ""}
            <button type="button" class="job-action" data-job-action="${paused ? "resume" : "pause"}">${paused ? "Resume" : "Pause"}</button>
            <button type="button" class="job-action" data-job-action="remove">Remove</button>
          </div>
        </article>
      `;
    }).join("");
  }

  async function loadJobs() {
    setTextIfChanged(els.jobsDialogStatus, "Loading jobs…");
    try {
      const result = await fetchJson("api/jobs");
      renderJobs(result.jobs);
      setTextIfChanged(
        els.jobsDialogStatus,
        `${result.jobs?.length || 0} configured job${result.jobs?.length === 1 ? "" : "s"}.`,
      );
    } catch (error) {
      setTextIfChanged(
        els.jobsDialogStatus,
        `Could not load jobs: ${String(error).replace(/^Error:\s*/, "")}`,
      );
    }
  }

  async function runJobCommand(payload, successText) {
    setTextIfChanged(els.jobsDialogStatus, "Running Prompta CLI command…");
    els.saveJobButton.disabled = true;
    try {
      const result = await postJson("api/jobs", payload);
      renderJobs(result.jobs);
      const command = Array.isArray(result.command) ? result.command.join(" ") : "";
      setTextIfChanged(els.jobsDialogStatus, command ? `${successText} · ${command}` : successText);
      return true;
    } catch (error) {
      setTextIfChanged(
        els.jobsDialogStatus,
        `Jobs command failed: ${String(error).replace(/^Error:\s*/, "")}`,
      );
      return false;
    } finally {
      els.saveJobButton.disabled = false;
    }
  }

  async function open(clearComposer = false) {
    if (clearComposer) {
      els.messageInput.value = "";
      els.slashMenu.hidden = true;
      resizeComposer();
      syncSendButton();
    }
    resetJobForm();
    if (!els.jobsDialog.open) {
      const stacked = mobileJobsScreen.matches;
      els.jobsDialog.dataset.presentation = stacked ? "stack" : "modal";
      if (stacked) {
        els.jobsDialog.show();
        if (appShell) appShell.inert = true;
      } else {
        els.jobsDialog.showModal();
      }
    }
    await loadJobs();
  }

  els.jobsSidebarButton.addEventListener("click", async () => {
    closeSidebar();
    await open();
  });
  els.closeJobsDialog.addEventListener("click", closeJobsView);
  els.jobsDialog.addEventListener("click", (event) => {
    if (event.target === els.jobsDialog && els.jobsDialog.dataset.presentation !== "stack") {
      closeJobsView();
    }
  });
  els.jobsDialog.addEventListener("close", () => {
    if (appShell) appShell.inert = false;
    delete els.jobsDialog.dataset.presentation;
  });
  els.jobScheduleType.addEventListener("change", syncJobScheduleFields);
  els.resetJobForm.addEventListener("click", resetJobForm);
  els.jobsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const daily = els.jobScheduleType.value === "daily";
    const payload = {
      action: "add",
      name: els.jobNameInput.value.trim(),
      prompt: els.jobPromptInput.value.trim(),
      daily_at: daily ? els.jobDailyInput.value : "",
      interval_minutes: daily ? null : Number(els.jobIntervalInput.value),
      exact_interval: !daily && els.jobExactInput.checked,
    };
    const saved = await runJobCommand(payload, `Saved ${payload.name}`);
    if (saved) resetJobForm();
  });
  els.jobsList.addEventListener("click", async (event) => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-job-action]");
    const row = button?.closest<HTMLElement>("[data-job-name]");
    if (!button || !row) return;
    const name = String(row.dataset.jobName || "");
    const job = scheduledJobs.find((item) => item.name === name);
    if (!job) return;
    const action = String(button.dataset.jobAction || "");
    if (action === "edit") {
      setTextIfChanged(els.jobsFormTitle, `Edit ${job.name}`);
      els.jobNameInput.value = job.name;
      els.jobNameInput.readOnly = true;
      els.jobPromptInput.value = job.prompt || "";
      els.jobScheduleType.value = job.daily_at ? "daily" : "interval";
      els.jobDailyInput.value = job.daily_at || "09:00";
      els.jobIntervalInput.value = String(job.interval_minutes || 30);
      els.jobExactInput.checked = Boolean(job.exact_interval);
      syncJobScheduleFields();
      els.jobPromptInput.focus();
      return;
    }
    await runJobCommand(
      { action, name },
      `${action === "remove" ? "Removed" : action === "pause" ? "Paused" : "Resumed"} ${name}`,
    );
  });
  els.clearJobsButton.addEventListener("click", async () => {
    if (!scheduledJobs.length) return;
    if (!window.confirm(`Clear all ${scheduledJobs.length} scheduled jobs?`)) return;
    const cleared = await runJobCommand({ action: "clear" }, "Cleared all scheduled jobs");
    if (cleared) resetJobForm();
  });

  function close() {
    closeJobsView();
  }

  return { open, close };
}
