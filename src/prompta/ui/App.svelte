<script lang="ts">
  import { onMount } from "svelte";
  import ChangelogDialog from "./ChangelogDialog.svelte";
  import Composer from "./Composer.svelte";
  import ConversationMessages from "./ConversationMessages.svelte";
  import JobsDialog from "./JobsDialog.svelte";
  import LogsPanel from "./LogsPanel.svelte";
  import SidebarList from "./SidebarList.svelte";
  import { appActions } from "./appActions.svelte";
  import {
    appViewState,
    requestSearchFocus,
  } from "./appViewState.svelte";
  import { getAttachmentPicker, getJobsDialog } from "./uiControllers";
  import {
    closeSidebar,
    finishSidebarMotion,
    openSidebar,
    sidebarState,
  } from "./sidebarState.svelte";

  let { serverName }: { serverName: string } = $props();
  let changelogDialog: { open: () => Promise<void> } | undefined;
  let searchInput: HTMLInputElement;
  let sidebarScroll: HTMLElement;
  let lastSearchFocusRequest = 0;
  let lastSidebarTopRequest = 0;

  const serverDisplay = $derived(appViewState.serverDisplay || serverName);

  function syncViewportHeight() {
    const viewportHeight = window.visualViewport?.height || window.innerHeight;
    document.documentElement.style.setProperty("--app-height", String(Math.round(viewportHeight)) + "px");
  }

  function handleGlobalKeydown(event: KeyboardEvent) {
    const target = event.target as HTMLElement | null;
    const typing =
      target instanceof HTMLInputElement ||
      target instanceof HTMLTextAreaElement ||
      Boolean(target?.isContentEditable);

    if (event.key === "/" && !typing) {
      event.preventDefault();
      openSidebar();
      requestSearchFocus();
      return;
    }

    if (event.key !== "Escape") return;

    if (document.activeElement === searchInput && appViewState.searchValue) {
      event.preventDefault();
      appViewState.searchValue = "";
      appActions.onSearch("");
      return;
    }

    getAttachmentPicker().closeMenu();
    getJobsDialog().close();
    searchInput?.blur();
    closeSidebar(true);
  }

  onMount(() => {
    if (appViewState.serverLabel === "Server · local") {
      appViewState.serverLabel = "Server · " + serverName;
    }

    syncViewportHeight();
    const visualViewport = window.visualViewport;
    const bootFallback = window.setTimeout(
      () => document.documentElement.classList.remove("booting"),
      1200,
    );
    visualViewport?.addEventListener("resize", syncViewportHeight);

    return () => {
      window.clearTimeout(bootFallback);
      visualViewport?.removeEventListener("resize", syncViewportHeight);
    };
  });

  $effect(() => {
    if (appViewState.bootComplete) document.documentElement.classList.remove("booting");
  });

  $effect(() => {
    const request = appViewState.searchFocusRequest;
    if (!searchInput || request === lastSearchFocusRequest) return;
    lastSearchFocusRequest = request;
    requestAnimationFrame(() => searchInput.focus({ preventScroll: true }));
  });

  $effect(() => {
    const request = appViewState.sidebarTopRequest;
    if (!sidebarScroll || request === lastSidebarTopRequest) return;
    lastSidebarTopRequest = request;
    requestAnimationFrame(() => {
      sidebarScroll.scrollTop = 0;
    });
  });
</script>

<svelte:head>
  <title>Prompta · {serverDisplay}</title>
  <meta name="apple-mobile-web-app-title" content={"Prompta " + serverDisplay} />
</svelte:head>

<svelte:window
  onkeydown={handleGlobalKeydown}
  onhashchange={appActions.onHashChange}
  onpagehide={appActions.onPageHide}
  onpageshow={appActions.onPageShow}
  onresize={syncViewportHeight}
/>

<div class="app-shell">
  <aside
    class={["sidebar", { "is-open": sidebarState.open }]}
    id="sidebar"
    ontransitionend={(event) => {
      if (event.propertyName === "transform") finishSidebarMotion();
    }}
  >
    <div class="sidebar-top">
      <div class="brand-row">
        <button
          class="icon-button mobile-only"
          id="closeSidebar"
          aria-label="Close sidebar"
          aria-controls="sidebar"
          onclick={() => closeSidebar()}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6"></path></svg>
        </button>
        <div class="brand-mark" aria-hidden="true">P</div>
        <div class="brand-copy">
          <strong>Prompta</strong>
          <span id="serverLabel">{appViewState.serverLabel}</span>
        </div>
        <div
          class={["live-orb", { live: appViewState.live }]}
          id="globalLiveOrb"
          title={appViewState.liveTitle}
        ></div>
      </div>
      <label class="search-box">
        <svg viewBox="0 0 24 24" aria-hidden="true"
          ><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg
        >
        <input
          bind:this={searchInput}
          bind:value={appViewState.searchValue}
          id="searchInput"
          type="search"
          placeholder="Search cached chats"
          aria-label="Search cached chats"
          aria-keyshortcuts="/"
          autocomplete="off"
          oninput={() => appActions.onSearch(appViewState.searchValue)}
        />
        <kbd>/</kbd>
      </label>
    </div>

    <div bind:this={sidebarScroll} class="sidebar-scroll">
      <button
        type="button"
        class="sidebar-action"
        id="jobsSidebarButton"
        onclick={() => void getJobsDialog().open()}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"
          ><path d="M7 3v3M17 3v3M4.5 8.5h15M6 5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"></path><path
            d="M8 12h3M8 16h3M14 12h2M14 16h2"
          ></path></svg
        >
        <span>Jobs</span>
      </button>
      <nav class="chat-list" id="chatList" aria-label="Cached conversations"><SidebarList /></nav>
    </div>

    <div class="sidebar-footer">
      <div class="cache-summary">
        <span class="summary-dot"></span>
        <span id="cacheSummary">{appViewState.cacheSummary}</span>
      </div>
      <button
        type="button"
        class="read-only-pill"
        id="headLabel"
        title={appViewState.headTitle}
        aria-haspopup="dialog"
        aria-controls="changelogDialog"
        onclick={() => void changelogDialog?.open()}
      >{appViewState.headLabel}</button>
    </div>
  </aside>

  <div
    class={["sidebar-scrim", { "is-open": sidebarState.open }]}
    id="sidebarScrim"
    role="button"
    tabindex="-1"
    aria-label="Close sidebar"
    onclick={() => closeSidebar()}
    onkeydown={(event) => {
      if (event.key === "Enter" || event.key === " ") closeSidebar();
    }}
  ></div>

  <main class="main-panel">
    <header class="topbar">
      <button
        class="icon-button mobile-only"
        id="openSidebar"
        aria-label="Open sidebar"
        aria-controls="sidebar"
        aria-expanded={sidebarState.open}
        onclick={openSidebar}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"
          ><path d="M4 7h16M4 12h16M4 17h16"></path></svg
        >
      </button>
      <div class="chat-heading" id="chatHeading">
        <div class="heading-title">{appViewState.headingTitle}</div>
        <div class="heading-meta">{appViewState.headingMeta}</div>
      </div>
      <div class="topbar-actions" aria-label="Prompta actions">
        <button
          class={["icon-button", { active: appViewState.pinActive }]}
          id="pinChatButton"
          aria-label={appViewState.pinLabel}
          title={appViewState.pinLabel}
          aria-pressed={appViewState.pinActive}
          disabled={appViewState.pinDisabled}
          onclick={appActions.onPin}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"
            ><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6ZM12 14v7"></path></svg
          >
        </button>
        <button
          class="icon-button"
          id="shareChatButton"
          aria-label="Copy chat link"
          title="Share chat"
          disabled={appViewState.shareDisabled}
          onclick={appActions.onShare}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"
            ><path d="M12 15V3M7 8l5-5 5 5M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7"></path></svg
          >
        </button>
        <span
          class={["status-icon", "sync", appViewState.syncStatus]}
          id="syncLabel"
          role="img"
          aria-label={appViewState.syncLabel}
          title={appViewState.syncLabel}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"
            ><path d="M5 6c0-1.1 3.1-2 7-2s7 .9 7 2-3.1 2-7 2-7-.9-7-2Zm0 0v6c0 1.1 3.1 2 7 2s7-.9 7-2V6M5 12v6c0 1.1 3.1 2 7 2s7-.9 7-2v-6"></path></svg
          >
        </span>
      </div>
    </header>

    <section
      class={["conversation-viewport", { "chat-switching": appViewState.chatSwitching }]}
      id="conversationViewport"
      aria-busy={appViewState.chatSwitching ? "true" : undefined}
      hidden={appViewState.mode === "logs"}
    >
      <div class="empty-state" id="emptyState" hidden={!appViewState.emptyVisible}>
        <div class="empty-logo">P</div>
        <h1>Your Prompta chats, locally.</h1>
        <p>Active runs and completed history stream from Prompta's SQLite cache.</p>
        <div class="empty-features">
          <span>Reply from here</span>
          <span>Live SSE updates</span>
          <span>SQLite source of truth</span>
        </div>
      </div>
      <article class="conversation" id="conversation" hidden={!appViewState.conversationVisible}>
        <ConversationMessages />
      </article>
    </section>

    <LogsPanel />

    {#if appViewState.mode === "chats"}
      <Composer />
    {/if}
  </main>
</div>

<button
  type="button"
  class="version-update-notice"
  id="versionUpdateNotice"
  aria-label={appViewState.updateApplying
    ? "Updating Prompta"
    : "New Prompta version available. Tap to update"}
  aria-live="polite"
  hidden={!appViewState.updateAvailable}
  disabled={appViewState.updateApplying}
  onclick={appActions.onApplyUpdate}
>{appViewState.updateApplying ? "Updating…" : "Update available"}</button>

<JobsDialog />
<ChangelogDialog bind:this={changelogDialog} />
