export type SidebarDragDirection = "pending" | "horizontal" | "vertical";

export function sidebarDragCanStart(wasOpen: boolean, clientX: number) {
  return wasOpen || clientX <= 144;
}

export function sidebarDragDirection(deltaX: number, deltaY: number): SidebarDragDirection {
  if (Math.max(Math.abs(deltaX), Math.abs(deltaY)) <= 8) return "pending";

  return Math.abs(deltaX) > Math.abs(deltaY) * 1.15 ? "horizontal" : "vertical";
}

export function sidebarDragPosition(
  wasOpen: boolean,
  width: number,
  startClientX: number,
  clientX: number,
) {
  const startX = wasOpen ? 0 : -width;
  const x = Math.max(-width, Math.min(0, startX + clientX - startClientX));
  const progress = width > 0 ? 1 + x / width : 0;

  return { x, progress: Math.max(0, Math.min(1, progress)) };
}

export function sidebarDragShouldOpen(velocityX: number, progress: number) {
  if (velocityX > 0.35) return true;

  if (velocityX < -0.35) return false;

  return progress >= 0.5;
}
