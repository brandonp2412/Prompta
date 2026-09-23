<script lang="ts">
  import { MediaQuery } from "svelte/reactivity";

  import { dialogVisibility } from "./browserAttachments.svelte";
  import { changelogEntries, type ChangelogEntry } from "./changelog";
  import { popStackPage, pushStackPage, stackPageFromState } from "./stackNavigation";
  import { registerChangelogDialog } from "./uiControllers";

  const mobile = new MediaQuery("(max-width: 600px)");
  let status = $state("Commit titles from this Prompta checkout.");
  let changes = $state.raw<ChangelogEntry[]>([]);
  let failed = $state(false);
  let open = $state(false);
  let presentation = $state<"modal" | "stack">("modal");

  async function load() {
    status = "Loading changelog…";
    failed = false;
    changes = [];

    try {
      const response = await fetch("api/changelog", { cache: "no-store" });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      changes = changelogEntries(await response.json());
      status = `${changes.length} commit${changes.length === 1 ? "" : "s"} · newest first`;
    } catch (error) {
      failed = true;
      status = "Changelog unavailable: " + String(error).replace(/^Error:\s*/, "");
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
    await load();
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
