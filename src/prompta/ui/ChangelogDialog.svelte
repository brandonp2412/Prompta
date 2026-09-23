<script lang="ts">
  import type { Attachment } from "svelte/attachments";
  import { MediaQuery } from "svelte/reactivity";

  import { dialogVisibility } from "./browserAttachments.svelte";
  import { changelogEntries, type ChangelogEntry } from "./changelog";
  import { registerChangelogDialog } from "./uiControllers";

  const mobile = new MediaQuery("(max-width: 600px)");
  let status = $state("Commit titles from this Prompta checkout.");
  let changes = $state.raw<ChangelogEntry[]>([]);
  let failed = $state(false);
  let open = $state(false);
  let presentation = $state<"modal" | "stack">("modal");
  let nextOffset = $state<number | null>(0);
  let loadingMore = $state(false);

  const PAGE_SIZE = 60;

  async function load(reset = false) {
    if (loadingMore || (!reset && nextOffset === null)) return;

    if (reset) {
      status = "Loading changelog…";
      failed = false;
      changes = [];
      nextOffset = 0;
    }

    const offset = reset ? 0 : nextOffset || 0;
    loadingMore = true;

    try {
      const response = await fetch(`api/changelog?limit=${PAGE_SIZE}&offset=${offset}`, {
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);

      const payload = await response.json();
      const page = changelogEntries(payload);
      const seen = new Set(changes.map((change) => `${change.hash || ""}:${change.title || ""}`));
      changes = [
        ...changes,
        ...page.filter((change) => !seen.has(`${change.hash || ""}:${change.title || ""}`)),
      ];
      const parsedOffset = Number(payload.next_offset);
      nextOffset =
        payload.next_offset !== null && Number.isFinite(parsedOffset) ? parsedOffset : null;
      status = `${changes.length}${nextOffset === null ? "" : "+"} commit${changes.length === 1 ? "" : "s"} · newest first`;
    } catch (error) {
      failed = true;
      status = "Changelog unavailable: " + String(error).replace(/^Error:\s*/, "");
    } finally {
      loadingMore = false;
    }
  }

  function loadMoreTrigger(): Attachment<HTMLElement> {
    return (element) => {
      if (typeof IntersectionObserver === "undefined") return;

      const root = element.closest(".changelog-list");
      const observer = new IntersectionObserver(
        (entries) => {
          if (entries.some((entry) => entry.isIntersecting) && nextOffset !== null && !loadingMore) {
            void load();
          }
        },
        { root, rootMargin: "320px 0px" },
      );
      observer.observe(element);

      return () => observer.disconnect();
    };
  }

  export async function show() {
    presentation = mobile.current ? "stack" : "modal";
    open = true;

    if (!changes.length || failed) await load(true);
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
        {#if nextOffset !== null}
          <li
            {@attach loadMoreTrigger()}
            class="changelog-load-more"
            aria-busy={loadingMore ? "true" : undefined}
          >
            {loadingMore ? "Loading older changes…" : ""}
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
