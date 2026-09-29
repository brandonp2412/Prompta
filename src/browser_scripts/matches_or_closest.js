(el, selector) => {
  for (let node = el; node; ) {
    if (node.matches?.(selector)) return true;
    if (node.assignedSlot) {
      node = node.assignedSlot;
      continue;
    }
    if (node.parentElement) {
      node = node.parentElement;
      continue;
    }
    const root = node.getRootNode?.();
    node = root && root !== document ? root.host || null : null;
  }
  return false;
}
