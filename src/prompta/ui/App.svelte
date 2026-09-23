<script lang="ts">
  import { MediaQuery } from "svelte/reactivity";
  import ChangelogDialog from "./ChangelogDialog.svelte";
  import Composer from "./Composer.svelte";
  import ConversationMessages from "./ConversationMessages.svelte";
  import JobsDialog from "./JobsDialog.svelte";
  import LogsPanel from "./LogsPanel.svelte";
  import SidebarList from "./SidebarList.svelte";
  import { appActions } from "./appActions.svelte";
  import {
    appViewState,
    requestSearchBlur,
    requestSearchFocus,
  } from "./appViewState.svelte";
  import {
    blurOnRequest,
    conversationViewport,
    fitVisualViewport,
    focusOnRequest,
    reportElementWidth,
    scrollToTopOnRequest,
  } from "./browserAttachments.svelte";
  import { getAttachmentPicker, getChangelogDialog, getJobsDialog } from "./uiControllers";
  import {
    closeSidebar,
    finishSidebarMotion,
    openSidebar,
    sidebarState,
  } from "./sidebarState.svelte";
  import {
    sidebarDragDirection,
    sidebarDragPosition,
    sidebarDragShouldOpen,
  } from "./sidebarGesture";

  let { serverName }: { serverName: string } = $props();

  const serverDisplay = $derived(appViewState.serverDisplay || serverName);
  const serverLabel = $derived(
    appViewState.serverLabel === "Server · local"
      ? "Server · " + serverName
      : appViewState.serverLabel,
  );

  const mobileSidebarMedia = new MediaQuery("(max-width: 780px)");
  let sidebarWidth = $state(0);
  let sidebarDragCleanupTimer: ReturnType<typeof setTimeout> | undefined;
  const sidebarDrag = $state({
    pointerId: null as number | null,
    startX: 0,
    startY: 0,
    lastX: 0,
    lastAt: 0,
    velocityX: 0,
    width: 0,
    wasOpen: false,
    active: false,
    settling: false,
    x: 0,
    progress: 0,
    duration: 0,
  });

  function mobileSidebarEnabled() {
    return mobileSidebarMedia.current;
  }

  function clearSidebarDrag() {
    if (sidebarDragCleanupTimer !== undefined) {
      clearTimeout(sidebarDragCleanupTimer);
      sidebarDragCleanupTimer = undefined;
    }

    sidebarDrag.pointerId = null;
    sidebarDrag.active = false;
    sidebarDrag.settling = false;
    sidebarDrag.width = 0;
    sidebarDrag.velocityX = 0;
    sidebarDrag.duration = 0;
  }

  function completeSidebarDrag() {
    const wasMoving = sidebarState.moving;
    clearSidebarDrag();
    if (wasMoving) finishSidebarMotion();
  }

  function settleSidebarDrag(opened: boolean) {
    const targetX = opened ? 0 : -sidebarDrag.width;
    const remaining = Math.abs(targetX - sidebarDrag.x);
    const speed = Math.max(0.6, Math.abs(sidebarDrag.velocityX));
    const duration = Math.max(90, Math.min(180, Math.round(remaining / speed)));

    sidebarState.open = opened;
    sidebarState.moving = true;
    sidebarDrag.settling = true;
    sidebarDrag.duration = duration;
    sidebarDrag.x = targetX;
    sidebarDrag.progress = opened ? 1 : 0;

    sidebarDragCleanupTimer = setTimeout(completeSidebarDrag, duration + 40);
  }

  function handleSidebarPointerDown(event: PointerEvent) {
    if (
      event.pointerType === "mouse" ||
      sidebarDrag.pointerId !== null ||
      sidebarDrag.active ||
      !mobileSidebarEnabled() ||
      sidebarWidth <= 0
    ) {
      return;
    }

    const width = sidebarWidth;
    const wasOpen = sidebarState.open;

    sidebarDrag.pointerId = event.pointerId;
    sidebarDrag.startX = event.clientX;
    sidebarDrag.startY = event.clientY;
    sidebarDrag.lastX = event.clientX;
    sidebarDrag.lastAt = performance.now();
    sidebarDrag.velocityX = 0;
    sidebarDrag.width = width;
    sidebarDrag.wasOpen = wasOpen;
    sidebarDrag.x = wasOpen ? 0 : -width;
    sidebarDrag.progress = wasOpen ? 1 : 0;
  }

  function handleSidebarPointerMove(event: PointerEvent) {
    if (event.pointerId !== sidebarDrag.pointerId) return;

    const deltaX = event.clientX - sidebarDrag.startX;
    const deltaY = event.clientY - sidebarDrag.startY;

    if (!sidebarDrag.active) {
      const direction = sidebarDragDirection(deltaX, deltaY);
      if (direction === "pending") return;

      if (direction === "vertical") {
        clearSidebarDrag();
        return;
      }

      if (!sidebarDrag.wasOpen && deltaX <= 0) return;

      sidebarDrag.active = true;
      sidebarState.moving = true;
    }

    event.preventDefault();

    const now = performance.now();
    const elapsed = Math.max(1, now - sidebarDrag.lastAt);
    const { x, progress } = sidebarDragPosition(
      sidebarDrag.wasOpen,
      sidebarDrag.width,
      sidebarDrag.startX,
      event.clientX,
    );

    sidebarDrag.velocityX = (event.clientX - sidebarDrag.lastX) / elapsed;
    sidebarDrag.lastX = event.clientX;
    sidebarDrag.lastAt = now;
    sidebarDrag.x = x;
    sidebarDrag.progress = progress;
  }

  function handleSidebarPointerUp(event: PointerEvent) {
    if (event.pointerId !== sidebarDrag.pointerId) return;

    if (!sidebarDrag.active) {
      clearSidebarDrag();
      return;
    }

    const { x, progress } = sidebarDragPosition(
      sidebarDrag.wasOpen,
      sidebarDrag.width,
      sidebarDrag.startX,
      event.clientX,
    );
    const now = performance.now();
    const elapsed = Math.max(1, now - sidebarDrag.lastAt);
    const finalVelocity = (event.clientX - sidebarDrag.lastX) / elapsed;

    sidebarDrag.x = x;
    sidebarDrag.progress = progress;
    if (Math.abs(finalVelocity) > Math.abs(sidebarDrag.velocityX)) {
      sidebarDrag.velocityX = finalVelocity;
    }

    settleSidebarDrag(sidebarDragShouldOpen(sidebarDrag.velocityX, progress));
  }

  function handleSidebarPointerCancel(event: PointerEvent) {
    if (event.pointerId !== sidebarDrag.pointerId) return;

    if (sidebarDrag.active) settleSidebarDrag(sidebarDrag.wasOpen);
    else clearSidebarDrag();
  }

  function handleSidebarTransitionEnd(event: TransitionEvent) {
    if (event.propertyName !== "transform") return;

    if (sidebarDrag.settling) completeSidebarDrag();
    else finishSidebarMotion();
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

    const searchTarget = target instanceof HTMLInputElement && target.id === "searchInput";

    if (searchTarget && appViewState.searchValue) {
      event.preventDefault();
      appViewState.searchValue = "";
      appActions.onSearch("");
      return;
    }

    getAttachmentPicker().closeMenu();
    getJobsDialog().close();
    getChangelogDialog().close();
    requestSearchBlur();
    closeSidebar(true);
  }
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
  onpointerdowncapture={handleSidebarPointerDown}
  onpointermovecapture={handleSidebarPointerMove}
  onpointerupcapture={handleSidebarPointerUp}
  onpointercancelcapture={handleSidebarPointerCancel}
/>

<div {@attach fitVisualViewport()} class="app-shell">
  <aside
    {@attach reportElementWidth((width) => (sidebarWidth = width))}
    class={["sidebar", { "is-open": sidebarState.open }]}
    id="sidebar"
    style:transform={sidebarDrag.active ? "translate3d(" + sidebarDrag.x + "px, 0, 0)" : undefined}
    style:transition={
      sidebarDrag.active
        ? sidebarDrag.settling
          ? "transform " + sidebarDrag.duration + "ms cubic-bezier(0.2, 0, 0, 1)"
          : "none"
        : undefined
    }
    ontransitionend={handleSidebarTransitionEnd}
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
          <span id="serverLabel">{serverLabel}</span>
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
          {@attach focusOnRequest(() => appViewState.searchFocusRequest)}
          {@attach blurOnRequest(() => appViewState.searchBlurRequest)}
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

    <div {@attach scrollToTopOnRequest(() => appViewState.sidebarTopRequest)} class="sidebar-scroll">
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
        onclick={() => void getChangelogDialog().open()}
      >{appViewState.headLabel}</button>
    </div>
  </aside>

  <div
    class={["sidebar-scrim", { "is-open": sidebarState.open }]}
    id="sidebarScrim"
    role="button"
    tabindex="-1"
    aria-label="Close sidebar"
    style:opacity={sidebarDrag.active ? String(sidebarDrag.progress) : undefined}
    style:transition={
      sidebarDrag.active
        ? sidebarDrag.settling
          ? "opacity " + sidebarDrag.duration + "ms linear"
          : "none"
        : undefined
    }
    style:pointer-events={sidebarDrag.active ? "none" : undefined}
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
      {@attach conversationViewport()}
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
<ChangelogDialog />
