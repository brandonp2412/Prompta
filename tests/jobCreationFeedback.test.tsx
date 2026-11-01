import React from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "bun:test";
import JobEditor from "../src/ui/JobEditor";
import { createJobsPageController } from "../src/ui/JobsPageController";
import type { Job } from "../src/ui/jobView";
import { activeToast } from "../src/ui/toast";

const job = (name: string): Job => ({
  images: [],
  name,
  created_order: 1,
  prompt: "Check a simple status.",
  status: "healthy",
  status_message: "",
  paused: false,
  run_at_epoch: null,
  pin_chat: false,
  daily_at: null,
  interval_minutes: 40,
  exact_interval: false,
  source_revision: "",
  next_due_at_epoch: 0,
  last_sent_at: 0,
  last_uncertain_send_at: 0,
});

function renderEditor(model: ReturnType<typeof createJobsPageController>) {
  const ref = () => {};
  render(
    <JobEditor
      model={model}
      refs={{
        editorPage: ref,
        editorForm: ref,
        nameInput: ref,
        promptInput: ref,
        imageInput: ref,
        imagePreviewList: ref,
        editorFooter: ref,
      }}
    />,
  );
}

afterEach(() => {
  cleanup();
  activeToast.value = null;
  window.history.replaceState(null, "", "/");
});

test("a successfully created job does not report its own name as a duplicate", async () => {
  const originalFetch = globalThis.fetch;
  const created = job("unique-new-job");
  const posts: unknown[] = [];
  globalThis.fetch = Object.assign(
    async (_url: string | URL | Request, init?: RequestInit) => {
      posts.push(JSON.parse(String(init?.body)));
      return Response.json({ jobs: [created] });
    },
    { preconnect: originalFetch.preconnect },
  );
  try {
    const model = createJobsPageController({});
    act(() => model.beginNew());
    renderEditor(model);
    await act(async () => {
      model.name.value = created.name;
      model.prompt.value = created.prompt;
    });
    expect(model.duplicateName.value).toBe(false);
    await act(async () => {
      await model.submit();
    });
    expect(posts).toHaveLength(1);
    expect(model.jobs.value.map((saved) => saved.name)).toEqual([created.name]);
    expect(activeToast.value?.message ?? "").not.toContain("already exists");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("a genuine existing name is rejected before submitting", async () => {
  const model = createJobsPageController({});
  model.jobs.value = [job("scheduled")];
  act(() => model.beginNew());
  renderEditor(model);
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "scheduled" } });
  expect(model.duplicateName.value).toBe(true);
  expect(screen.getByRole("button", { name: "Create job" }).hasAttribute("disabled")).toBe(true);
  expect(activeToast.value?.message).toContain("already exists");
});
