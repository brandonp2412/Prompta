<script lang="ts">
  import JobsPage from "./JobsPage.svelte";
  import { appActions } from "./appActions.svelte";
  import { appViewState } from "./appViewState.svelte";
</script>

<section class="prompta-page" aria-labelledby="promptaPageTitle">
  <div class="prompta-page-shell">
    <section class="prompta-mode-card">
      <div class="prompta-section-heading">
        <div>
          <h2 id="promptaPageTitle">Prompta</h2>
          <p>Runtime controls and scheduled jobs.</p>
        </div>
        <span class="prompta-mode-state">{appViewState.unattended ? "ON" : "OFF"}</span>
      </div>

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
        <span>
          <strong>Machine Gun Mode</strong>
          <small>
            {appViewState.unattended
              ? `Dispatching without result polling · ${appViewState.unattendedSendGapSeconds}s gap`
              : "Normal result polling"}
          </small>
        </span>
      </button>
    </section>

    <JobsPage />
  </div>
</section>
