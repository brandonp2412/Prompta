<script lang="ts">
  import { MediaQuery } from "svelte/reactivity";

  import { dialogVisibility } from "./browserAttachments.svelte";
  import { changelogPage, type ChangelogEntry } from "./changelog";
  import { registerChangelogDialog } from "./uiControllers";

  const CHANGELOG_PAGE_SIZE = 100;
  const mobile = new MediaQuery("(max-width: 600px)");
  let status = $state("Commit titles from this Prompta checkout.");
  let changes = $state.raw<ChangelogEntry[]>([]);
  let failed = $state(false);
  let hasMore = $state(false);
  let loadingMore = $state(false);
  let currentLimit = $state(CHANGELOG_PAGE_SIZE);
  let open = $state(false);
  let presentation = $state<"modal" | "stack">("modal");

  async function load(limit: number, reset = false) {
    if (reset) {
      status = "Loading changelog…";
      failed = false;
      changes = [];
    }

    try {
      const response = await fetch("api/changelog?limit=" + limit, { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status) + " " + response.statusText);
      const page = changelogPage(await response.json());
      changes = page.changes;
      hasMore = page.hasMore;
      failed = false;
      status =
        "Showing " + changes.length + " of " + page.total + " commits · newest first";
    } catch (error) {
      failed = reset;
      if (reset) hasMore = false;
      status =
        (reset ? "Changelog unavailable: " : "Could not load older changes: ") +
        String(error).replace(/^Error:\s*/, "");
    }
  }

  async function loadMore() {
    if (loadingMore || !hasMore) return;

    loadingMore = true;
    currentLimit += CHANGELOG_PAGE_SIZE;
    try {
      await load(currentLimit);
    } finally {
      loadingMore = false;
    }
  }

  export async function show() {
    presentation = mobile.current ? "stack" : "modal";
    currentLimit = CHANGELOG_PAGE_SIZE;
    open = true;
    await load(currentLimit, true);
  }

  export function close() {
    open = false;
  }

  registerChangelogDialog({ open: show, close });
</script>

<dialog
  {@attach dialogVisibility(() => open, () => presentation === "modal", close)}
  class="changelog-dialog"
  id="changelogDialog"
  aria-labelledby="changelogDialogTitle"
  data-presentation={presentation}
  onclick={(event) => {
    if (event.target === event.currentTarget && presentation !== "stack") close();
  }}
>
  <div class="changelog-dialog-shell">
    <header class="changelog-dialog-header">
      <div>
        <h2 id="changelogDialogTitle">Changelog</h2>
        <p id="changelogDialogStatus">{status}</p>
      </div>
      <button
        type="button"
        class="changelog-close-button"
        id="closeChangelogDialog"
        aria-label="Close changelog"
        onclick={close}
      >
        ×
      </button>
    </header>
    <ol class="changelog-list" id="changelogList">
      {#if failed}
        <li class="changelog-empty">Could not load changelog.</li>
      {:else if changes.length}
        {#each changes as change ((change.hash || "") + (change.title || ""))}
          <li class="changelog-entry">
            <span class="changelog-entry-title">{change.title || ""}</span>
            {#if change.hash}<span class="changelog-entry-hash">#{change.hash}</span>{/if}
          </li>
        {/each}
        {#if hasMore}
          <li class="changelog-load-more-row">
            <button
              type="button"
              class="changelog-load-more"
              disabled={loadingMore}
              aria-busy={loadingMore}
              onclick={loadMore}
            >
              {loadingMore ? "Loading older changes…" : "Load older changes"}
            </button>
          </li>
        {/if}
      {:else}
        <li class="changelog-empty">
          {status.startsWith("Loading")
            ? "Loading changes…"
            : "No Git commit history is available."}
        </li>
      {/if}
    </ol>
  </div>
</dialog>
