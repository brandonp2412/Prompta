import { batch } from "@preact/signals-core";

type Swipe = {
  identifier: number;
  x: number;
  y: number;
  opening: boolean;
  width: number;
  progress: number;
  locked: boolean;
  rejected: boolean;
  lastX: number;
  lastTime: number;
  velocityX: number;
};

export function createDrawerSwipe({
  drawerOpen,
  drawerProgress,
  isList,
  drawerWidth,
  drawerPosition,
  onProgress,
  clock = performance,
}: {
  drawerOpen: { value: boolean };
  drawerProgress: { value: number | null };
  isList: () => boolean;
  drawerWidth: () => number;
  drawerPosition?: () => number;
  onProgress?: (progress: number, width: number) => void;
  clock?: { now: () => number };
}) {
  let swipe: Swipe | null = null;

  const clampDrawer = (value: number) => Math.max(0, Math.min(1, value));

  function cancelSwipe() {
    swipe = null;
    drawerProgress.value = null;
  }

  function startSwipe(event: TouchEvent) {
    if (swipe || !window.matchMedia("(max-width: 680px)").matches || event.touches.length !== 1)
      return;
    const touch = event.touches[0];
    const target = event.target;
    // This listener is global; modal and editable gestures belong to their controls.
    if (
      target &&
      "closest" in target &&
      typeof target.closest === "function" &&
      target.closest(
        ".settings-backdrop, .sidebar-profile-menu, input, textarea, select, [contenteditable]:not([contenteditable='false']), pre",
      )
    )
      return;
    if (isList() || (!drawerOpen.value && touch.clientX > 120)) return;
    swipe = {
      identifier: touch.identifier,
      x: touch.clientX,
      y: touch.clientY,
      opening: !drawerOpen.value,
      width: drawerWidth(),
      progress: clampDrawer(drawerPosition?.() ?? (drawerOpen.value ? 1 : 0)),
      locked: false,
      rejected: false,
      lastX: touch.clientX,
      lastTime: clock.now(),
      velocityX: 0,
    };
  }

  function moveSwipe(event: TouchEvent) {
    const gesture = swipe;
    if (!gesture || gesture.rejected) return;
    if (event.touches.length !== 1 || event.touches[0].identifier !== gesture.identifier) {
      cancelSwipe();
      return;
    }
    const touch = event.touches[0];
    const dx = touch.clientX - gesture.x;
    const dy = touch.clientY - gesture.y;
    if (!gesture.locked) {
      // Cancel the first horizontal movement before the browser starts scrolling.
      if (Math.abs(dx) > Math.abs(dy) && (gesture.opening ? dx > 0 : dx < 0))
        event.preventDefault();
      if (Math.max(Math.abs(dx), Math.abs(dy)) < 4) return;
      if (Math.abs(dy) >= Math.abs(dx) / 1.15) {
        gesture.rejected = true;
        return;
      }
      if ((gesture.opening && dx <= 0) || (!gesture.opening && dx >= 0)) return;
      gesture.locked = true;
    }
    // Own only horizontal gestures; leave vertical chat scrolling and text inputs alone.
    event.preventDefault();
    const now = clock.now();
    const dt = now - gesture.lastTime;
    if (dt > 0) {
      const instantVelocity = (touch.clientX - gesture.lastX) / dt;
      gesture.velocityX = gesture.velocityX * 0.35 + instantVelocity * 0.65;
    }
    gesture.lastX = touch.clientX;
    gesture.lastTime = now;
    const progress = clampDrawer(gesture.progress + dx / gesture.width);
    // The UI can paint touch positions directly without re-rendering the page
    // on every event. Keep the signal path for consumers without a painter.
    if (onProgress) onProgress(progress, gesture.width);
    else drawerProgress.value = progress;
  }

  function finishSwipe(event: TouchEvent) {
    const gesture = swipe;
    if (!gesture) return;
    const touch = Array.from(event.changedTouches).find(
      (item) => item.identifier === gesture.identifier,
    );
    if (!touch) return;
    batch(() => {
      if (gesture.locked) {
        const dx = touch.clientX - gesture.x;
        const progress = clampDrawer(gesture.progress + dx / gesture.width);
        const fling =
          Math.abs(dx) >= 30 &&
          Math.abs(gesture.velocityX) >= 0.45 &&
          clock.now() - gesture.lastTime < 120;
        if (fling) drawerOpen.value = gesture.velocityX > 0;
        else if (gesture.opening) drawerOpen.value = progress >= 0.35;
        else drawerOpen.value = progress > 0.65;
      }
      cancelSwipe();
    });
  }

  return { cancelSwipe, startSwipe, moveSwipe, finishSwipe };
}
