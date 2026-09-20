const sidebar = document.querySelector("#sidebar");
const body = document.body;
const drag = {
  id: null,
  startX: 0,
  startY: 0,
  lastX: 0,
  lastAt: 0,
  width: 0,
  open: false,
  active: false,
  frame: null,
  pendingX: 0,
};

function sidebarWidth() {
  return sidebar?.getBoundingClientRect().width || Math.min(innerWidth * 0.86, 320);
}

function setDrag(clientX) {
  const width = drag.width || sidebarWidth();
  const base = drag.open ? 0 : -width;
  const x = Math.max(-width, Math.min(0, base + clientX - drag.startX));
  const progress = Math.max(0, Math.min(1, (x + width) / width));
  body.style.setProperty("--sidebar-drag-x", x + "px");
  body.style.setProperty("--sidebar-drag-progress", String(progress));
}

function scheduleDrag(clientX) {
  drag.pendingX = clientX;
  if (drag.frame !== null) return;
  drag.frame = requestAnimationFrame(() => {
    drag.frame = null;
    setDrag(drag.pendingX);
  });
}

function finishDrag(clientX, cancelled) {
  if (drag.id === null) return;
  if (drag.frame !== null) {
    cancelAnimationFrame(drag.frame);
    drag.frame = null;
  }
  setDrag(clientX);
  const width = drag.width || sidebarWidth();
  const x = Math.max(-width, Math.min(0, (drag.open ? 0 : -width) + clientX - drag.startX));
  const progress = (x + width) / width;
  const elapsed = Math.max(1, performance.now() - drag.lastAt);
  const velocity = (clientX - drag.lastX) / elapsed;
  const open = cancelled ? drag.open : velocity > 0.5 || (velocity >= -0.5 && progress >= 0.42);
  body.classList.toggle("sidebar-open", open);
  requestAnimationFrame(() => {
    body.classList.remove("sidebar-dragging");
    body.style.removeProperty("--sidebar-drag-x");
    body.style.removeProperty("--sidebar-drag-progress");
  });
  drag.id = null;
  drag.width = 0;
  drag.active = false;
}

document.addEventListener("pointerdown", (event) => {
  if (event.pointerType === "mouse" || !matchMedia("(max-width: 900px)").matches) return;
  const width = sidebarWidth();
  drag.width = width;
  drag.open = body.classList.contains("sidebar-open");
  if (!drag.open && event.clientX > Math.min(112, innerWidth * 0.3)) return;
  if (drag.open && event.clientX > width + 24) return;
  drag.id = event.pointerId;
  drag.startX = drag.lastX = event.clientX;
  drag.startY = event.clientY;
  drag.lastAt = performance.now();
}, { passive: true });

document.addEventListener("pointermove", (event) => {
  if (event.pointerId !== drag.id) return;
  const dx = event.clientX - drag.startX;
  const dy = event.clientY - drag.startY;
  if (!drag.active) {
    if (Math.abs(dx) < 7 && Math.abs(dy) < 7) return;
    if (Math.abs(dy) > Math.abs(dx)) return finishDrag(drag.lastX, true);
    drag.active = true;
    body.classList.add("sidebar-dragging");
  }
  event.preventDefault();
  scheduleDrag(event.clientX);
  drag.lastX = event.clientX;
  drag.lastAt = performance.now();
}, { passive: false });

document.addEventListener("pointerup", (event) => {
  if (event.pointerId === drag.id) finishDrag(event.clientX, false);
});

document.addEventListener("pointercancel", (event) => {
  if (event.pointerId === drag.id) finishDrag(drag.lastX, true);
});
