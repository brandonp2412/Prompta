(element) => {
  let active = document.activeElement;
  while (active?.shadowRoot?.activeElement) {
    active = active.shadowRoot.activeElement;
  }
  if (!active) return false;
  if (active !== element && !active.isContentEditable) return false;
  for (let current = active; current; ) {
    if (current === element) return true;
    current = current.assignedSlot || current.parentElement || current.getRootNode?.().host || null;
  }
  return false;
}
