function requiredElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);

  if (!element) throw new Error(`Missing required sidebar UI element: ${selector}`);

  return element;
}

export function createSidebar({ onMotionEnd }) {
  const els = {
    sidebar: requiredElement<HTMLElement>("#sidebar"),
    openSidebar: requiredElement<HTMLButtonElement>("#openSidebar"),
    closeSidebar: requiredElement<HTMLButtonElement>("#closeSidebar"),
    sidebarScrim: requiredElement<HTMLElement>("#sidebarScrim"),
  };
  const mobileSidebarMedia = window.matchMedia("(max-width: 780px)");
  const swipe = {
    startX: 0,
    startY: 0,
    lastX: 0,
    lastTime: 0,
    velocityX: 0,
    sidebarWidth: 0,
    progress: 0,
    wasOpen: false,
    tracking: false,
    directionLocked: false,
    horizontal: false,
    frameId: 0,
    pendingX: 0,
    cleanupTimer: 0,
  };
  let moving = false;

  function isOpen() {
    return els.sidebar.classList.contains("is-open");
  }

  function isMoving() {
    return moving;
  }

  function beginMotion() {
    moving = true;
  }

  function endMotion() {
    if (!moving) return;

    moving = false;
    syncSidebarVisibility();
    onMotionEnd();
  }

  function mobileEnabled() {
    return mobileSidebarMedia.matches;
  }

  function sidebarHidden() {
    return mobileSidebarMedia.matches && !isOpen();
  }

  function syncExpandedState() {
    els.openSidebar.setAttribute("aria-expanded", String(!sidebarHidden()));
  }

  function syncSidebarVisibility() {
    const hidden = sidebarHidden();
    els.sidebar.toggleAttribute("inert", hidden);

    if (hidden) els.sidebar.setAttribute("aria-hidden", "true");
    else els.sidebar.removeAttribute("aria-hidden");
  }

  function syncAccessibility() {
    syncExpandedState();
    syncSidebarVisibility();
  }

  function resetDragStyles() {
    if (swipe.frameId) {
      cancelAnimationFrame(swipe.frameId);
      swipe.frameId = 0;
    }

    if (swipe.cleanupTimer) {
      clearTimeout(swipe.cleanupTimer);
      swipe.cleanupTimer = 0;
    }

    els.sidebar.style.removeProperty("transition");
    els.sidebar.style.removeProperty("transform");
    els.sidebarScrim.style.removeProperty("transition");
    els.sidebarScrim.style.removeProperty("opacity");
    endMotion();
  }

  function open() {
    resetDragStyles();

    const animate = mobileEnabled() && !isOpen();

    if (animate) beginMotion();

    els.sidebar.classList.add("is-open");
    els.sidebarScrim.classList.add("is-open");
    syncExpandedState();

    if (!animate) syncSidebarVisibility();
  }

  function close() {
    resetDragStyles();

    const animate = mobileEnabled() && isOpen();

    if (animate) beginMotion();

    els.sidebar.classList.remove("is-open");
    els.sidebarScrim.classList.remove("is-open");
    syncExpandedState();

    if (!animate) syncSidebarVisibility();
  }

  function applyDragPosition(x) {
    const width = swipe.sidebarWidth || els.sidebar.getBoundingClientRect().width;
    swipe.progress = Math.max(0, Math.min(1, 1 + x / width));
    els.sidebar.style.transform = `translate3d(${x}px, 0, 0)`;
    els.sidebarScrim.style.opacity = String(swipe.progress);
  }

  function queueDragPosition(x) {
    swipe.pendingX = x;

    if (swipe.frameId) return;

    swipe.frameId = requestAnimationFrame(() => {
      swipe.frameId = 0;
      applyDragPosition(swipe.pendingX);
    });
  }

  function settleDrag(opened) {
    const width = swipe.sidebarWidth || els.sidebar.getBoundingClientRect().width;

    if (swipe.frameId) {
      cancelAnimationFrame(swipe.frameId);
      swipe.frameId = 0;
      applyDragPosition(swipe.pendingX);
    }

    const currentX = -width * (1 - swipe.progress);
    const targetX = opened ? 0 : -width;
    const remaining = Math.abs(targetX - currentX);
    const speed = Math.max(0.6, Math.abs(swipe.velocityX));
    const duration = Math.max(90, Math.min(180, Math.round(remaining / speed)));
    els.sidebar.classList.toggle("is-open", opened);
    els.sidebarScrim.classList.toggle("is-open", opened);
    syncExpandedState();
    els.sidebar.style.transition = `transform ${duration}ms cubic-bezier(0.2, 0, 0, 1)`;
    els.sidebar.style.transform = `translate3d(${targetX}px, 0, 0)`;
    els.sidebarScrim.style.transition = `opacity ${duration}ms linear`;
    els.sidebarScrim.style.opacity = opened ? "1" : "0";

    if (swipe.cleanupTimer) clearTimeout(swipe.cleanupTimer);

    swipe.cleanupTimer = window.setTimeout(() => {
      swipe.cleanupTimer = 0;
      els.sidebar.style.removeProperty("transition");
      els.sidebar.style.removeProperty("transform");
      els.sidebarScrim.style.removeProperty("transition");
      els.sidebarScrim.style.removeProperty("opacity");
      endMotion();
    }, duration + 30);
  }

  els.openSidebar.addEventListener("click", open);
  els.closeSidebar.addEventListener("click", close);
  els.sidebarScrim.addEventListener("click", close);
  mobileSidebarMedia.addEventListener("change", syncAccessibility);
  window.addEventListener("resize", syncAccessibility);
  syncAccessibility();

  els.sidebar.addEventListener("transitionrun", (event) => {
    if (event.propertyName === "transform" && mobileEnabled()) beginMotion();
  });
  els.sidebar.addEventListener("transitionend", (event) => {
    if (event.propertyName === "transform") endMotion();
  });
  els.sidebar.addEventListener("transitioncancel", (event) => {
    if (event.propertyName === "transform") endMotion();
  });

  document.addEventListener(
    "touchstart",
    (event) => {
      if (!mobileEnabled() || event.touches.length !== 1) return;

      resetDragStyles();
      const touch = event.touches[0];
      const sidebarOpen = isOpen();

      if (!sidebarOpen && touch.clientX > 144) return;

      swipe.startX = touch.clientX;
      swipe.startY = touch.clientY;
      swipe.lastX = touch.clientX;
      swipe.lastTime = performance.now();
      swipe.velocityX = 0;
      swipe.sidebarWidth = els.sidebar.getBoundingClientRect().width;
      swipe.progress = sidebarOpen ? 1 : 0;
      swipe.wasOpen = sidebarOpen;
      swipe.tracking = true;
      swipe.directionLocked = false;
      swipe.horizontal = false;
      swipe.pendingX = sidebarOpen ? 0 : -swipe.sidebarWidth;
    },
    { passive: true },
  );

  document.addEventListener(
    "touchmove",
    (event) => {
      if (!swipe.tracking || event.touches.length !== 1) return;

      const touch = event.touches[0];
      const deltaX = touch.clientX - swipe.startX;
      const deltaY = touch.clientY - swipe.startY;

      if (!swipe.directionLocked && (Math.abs(deltaX) > 8 || Math.abs(deltaY) > 8)) {
        swipe.directionLocked = true;
        swipe.horizontal = Math.abs(deltaX) > Math.abs(deltaY) * 1.15;

        if (swipe.horizontal) {
          beginMotion();
          els.sidebar.style.transition = "none";
          els.sidebarScrim.style.transition = "none";
        }
      }

      if (!swipe.horizontal) return;

      const width = swipe.sidebarWidth;
      const startX = swipe.wasOpen ? 0 : -width;
      const x = Math.max(-width, Math.min(0, startX + deltaX));
      const now = performance.now();
      const elapsed = Math.max(1, now - swipe.lastTime);
      swipe.velocityX = (touch.clientX - swipe.lastX) / elapsed;
      swipe.lastX = touch.clientX;
      swipe.lastTime = now;
      queueDragPosition(x);
    },
    { passive: true },
  );

  document.addEventListener(
    "touchend",
    () => {
      if (!swipe.tracking) return;

      if (swipe.horizontal) {
        const fastOpen = swipe.velocityX > 0.35;
        const fastClose = swipe.velocityX < -0.35;
        const shouldOpen = fastOpen || (!fastClose && swipe.progress >= 0.5);
        settleDrag(shouldOpen);
      }

      swipe.tracking = false;
    },
    { passive: true },
  );

  document.addEventListener(
    "touchcancel",
    () => {
      if (swipe.tracking && swipe.horizontal) settleDrag(swipe.wasOpen);

      swipe.tracking = false;
    },
    { passive: true },
  );

  return { open, close, isMoving };
}
