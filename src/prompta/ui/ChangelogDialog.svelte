<script lang="ts">
  import { MediaQuery } from "svelte/reactivity";

  import { dialogVisibility, scrollNearBottom } from "./browserAttachments.svelte";
  import { changelogEntries, changelogHasMore, type ChangelogEntry } from "./changelog";
  import { popStackPage, pushStackPage, stackPageFromState } from "./stackNavigation";
  import { registerChangelogDialog } from "./uiControllers";

  const mobile = new MediaQuery("(max-width: 600px)");
  const pageSize = 100;
  let status = $state("Commit titles from this Prompta checkout.");
  let changes = $state.raw<ChangelogEntry[]>([]);
  let failed = $state(false);
  let loading = $state(false);
  let hasMore = $state(true);
  let open = $state(false);
  let presentation = $state<"modal" | "stack">("modal");

  async function load() {
    if (loading || !hasMore) return;

    loading = true;
    failed = false;
    if (!changes.length) status = "Loading changelog…";

    try {
      const response = await fetch(
        `api/changelog?limit=${pageSize}&offset=${changes.length}`,
        { cache: "no-store" },
      );
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);

      const payload: unknown = await response.json();
      const page = changelogEntries(payload);
      changes = [...changes, ...page];
      hasMore = changelogHasMore(payload);
      status = `${changes.length}${hasMore ? "+" : ""} commit${changes.length === 1 && !hasMore ? "" : "s"} · newest first`;
    } catch (error) {
      failed = changes.length === 0;
      status = "Changelog unavailable: " + String(error).replace(/^Error:\s*/, "");
    } finally {
      loading = false;
    }
  }

  function handlePopState(event: PopStateEvent) {
    if (presentation !== "stack") return;

    open = stackPageFromState(event.state) === "changelog";
  }

  export async function show() {
    presentation = mobile.current ? "stack" : "modal";

    if (presentation === "stack" && stackPageFromState(history.state) !== "changelog") {
      pushStackPage("changelog");
    }

    open = true;
    if (!changes.length && !loading) await load();
  }

  export function close() {
    if (presentation === "stack" && open && popStackPage("changelog")) return;

    open = false;
  }

  registerChangelogDialog({ open: show, close });
</script>

<svelte:window onpopstate={handlePopState} />

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
    <ol {@attach scrollNearBottom(() => void load())} class="changelog-list" id="changelogList">
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
          <li class="changelog-load-more">
            <button type="button" disabled={loading} onclick={() => void load()}>
              {loading ? "Loading older commits…" : "Load older commits"}
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
