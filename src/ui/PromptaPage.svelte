<script lang="ts">
  import { MediaQuery } from "svelte/reactivity";

  import JobsPage from "./JobsPage.svelte";
  import { appActions } from "./appActions.svelte";
  import { appViewState } from "./appViewState.svelte";
  import { popStackPage, pushStackPage, stackPageFromState } from "./stackNavigation";

  const mobile = new MediaQuery("(max-width: 600px)");
  let presentation = $state<"page" | "stack">("page");

  $effect(() => {
    presentation = mobile.current ? "stack" : "page";

    if (presentation === "stack" && stackPageFromState(history.state) !== "prompta") {
      pushStackPage("prompta");
    }
  });

  function close() {
    if (presentation === "stack" && popStackPage("prompta")) return;

    appActions.onPromptaPageClose();
  }

  function handlePopState(event: PopStateEvent) {
    if (presentation !== "stack") return;
    if (stackPageFromState(event.state) === "prompta") return;

    appActions.onPromptaPageClose();
  }
</script>

<svelte:window onpopstate={handlePopState} />

<section
  class="prompta-page"
  aria-labelledby="promptaPageTitle"
  data-presentation={presentation}
>
  <div class="prompta-page-shell">
    <header class="prompta-page-header">
      <button
        type="button"
        class="prompta-back-button"
        aria-label="Back to chats"
        onclick={close}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M22 12H3m7.5-7.5L3 12l7.5 7.5"></path>
        </svg>
      </button>
      <div>
        <h2 id="promptaPageTitle">Prompta</h2>
        <p>Runtime controls and scheduled jobs.</p>
      </div>
    </header>

    <section class="prompta-mode-section" aria-labelledby="machineGunModeTitle">
      <button
        type="button"
        class={["prompta-machine-gun", { active: appViewState.unattended }]}
        id="machineGunModeButton"
        aria-label={appViewState.unattended ? "Disable Machine Gun Mode" : "Enable Machine Gun Mode"}
        title={
          appViewState.unattended
            ? "Machine Gun Mode on · no result polling · " +
              appViewState.unattendedSendGapSeconds +
              "s send gap"
            : "Machine Gun Mode · keep dispatching all jobs without reading results"
        }
        aria-pressed={appViewState.unattended}
        disabled={appViewState.unattendedUpdating}
        onclick={appActions.onUnattendedMode}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M2.5 8.5h9.25M2.5 11h9.25M2.5 13.5h9.25M2.5 7v8"></path>
          <circle cx="15" cy="11" r="3.5"></circle>
          <circle cx="15" cy="11" r="1"></circle>
          <path d="M18.5 9.5H21l1 1.5-1 1.5h-2.5M14 14.4 12.5 19h5L16 14.4"></path>
        </svg>
        <span class="prompta-machine-gun-copy">
          <strong id="machineGunModeTitle">Machine Gun Mode</strong>
          <small>
            {appViewState.unattended
              ? "Dispatching without result polling · " +
                appViewState.unattendedSendGapSeconds +
                "s gap"
              : "Normal result polling"}
          </small>
        </span>
        <span class="prompta-mode-state">{appViewState.unattended ? "ON" : "OFF"}</span>
      </button>
    </section>

    <JobsPage />
  </div>
</section>
