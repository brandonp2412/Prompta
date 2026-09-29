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
  const isRenderedWithin = (root, node) => {
    const start = node?.nodeType === Node.TEXT_NODE ? composedParent(node) : node;
    if (!start) return false;
    for (
      let current = start;
      current && current !== root && current.nodeType === Node.ELEMENT_NODE;
      current = composedParent(current)
    ) {
      if (
        current.hidden
        || normalise(current.getAttribute?.('aria-hidden')).toLowerCase() === 'true'
      ) return false;
      const style = getComputedStyle(current);
      if (
        style.display === 'none'
        || style.visibility === 'hidden'
        || style.visibility === 'collapse'
        || Number(style.opacity) === 0
        || style.contentVisibility === 'hidden'
      ) return false;
    }
    return true;
  };
  const renderedTextContent = (root, node = root) => {
    if (!node || !isRenderedWithin(root, node)) return '';
    if (node.nodeType === Node.TEXT_NODE) return node.nodeValue || '';
    return composedChildNodes(node)
      .map(child => renderedTextContent(root, child))
      .join('');
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
    el?.getAttribute?.('aria-description') || '',
    ...String(el?.getAttribute?.('aria-describedby') || '')
      .split(/\s+/)
      .filter(Boolean)
      .map(id => composedTextContent(referencedElement(id))),
    ...[...(el?.labels || [])].map(label => composedTextContent(label)),
    el?.getAttribute?.('aria-roledescription') || '',
    el?.getAttribute?.('title') || '',
    el?.getAttribute?.('alt') || '',
    el?.getAttribute?.('value') || '',
    el?.getAttribute?.('placeholder') || '',
    renderedTextContent(el),
  ].map(normalise).filter(Boolean);
  return [...new Set(labels)];
}
