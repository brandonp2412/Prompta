el => {
  const normalise = value => String(value || '').replace(/\s+/g, ' ').trim();
  const composedParent = node => {
    if (!node) return null;
    if (node.assignedSlot) return node.assignedSlot;
    if (node.parentElement) return node.parentElement;
    const root = node.getRootNode?.();
    return root && root !== document ? root.host || null : null;
  };
  const composedChildNodes = node => {
    if (!node) return [];
    if (node.tagName === 'SLOT') {
      const assigned = node.assignedNodes?.({flatten: true}) || [];
      if (assigned.length) return [...assigned];
    }
    if (node.shadowRoot) return [...node.shadowRoot.childNodes];
    return [...(node.childNodes || [])];
  };
  const composedTextContent = node => {
    if (!node) return '';
    if (node.nodeType === Node.TEXT_NODE) return node.nodeValue || '';
    return composedChildNodes(node).map(composedTextContent).join('');
  };
  const referencedElement = id => {
    const seenRoots = new Set();
    for (let current = el; current; current = composedParent(current)) {
      const root = current.getRootNode?.();
      if (!root || seenRoots.has(root)) continue;
      seenRoots.add(root);
      const match = root.getElementById?.(id);
      if (match) return match;
    }
    return document.getElementById(id);
  };
  const labels = [
    el?.getAttribute?.('aria-label') || '',
    ...String(el?.getAttribute?.('aria-labelledby') || '')
      .split(/\s+/)
      .filter(Boolean)
      .map(id => composedTextContent(referencedElement(id))),
    ...String(el?.getAttribute?.('aria-describedby') || '')
      .split(/\s+/)
      .filter(Boolean)
      .map(id => composedTextContent(referencedElement(id))),
    el?.getAttribute?.('aria-roledescription') || '',
    el?.getAttribute?.('title') || '',
    el?.getAttribute?.('alt') || '',
    el?.getAttribute?.('value') || '',
    composedTextContent(el),
  ].map(normalise).filter(Boolean);
  return [...new Set(labels)];
}
