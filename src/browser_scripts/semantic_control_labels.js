el => {
  const normalise = value => String(value || '').replace(/\s+/g, ' ').trim();
  const referencedElement = id => {
    const root = el?.getRootNode?.();
    return root?.getElementById?.(id) || document.getElementById(id);
  };
  const labels = [
    el?.getAttribute?.('aria-label') || '',
    ...String(el?.getAttribute?.('aria-labelledby') || '')
      .split(/\s+/)
      .filter(Boolean)
      .map(id => referencedElement(id)?.textContent || ''),
    ...String(el?.getAttribute?.('aria-describedby') || '')
      .split(/\s+/)
      .filter(Boolean)
      .map(id => referencedElement(id)?.textContent || ''),
    el?.getAttribute?.('aria-roledescription') || '',
    el?.getAttribute?.('title') || '',
    el?.getAttribute?.('alt') || '',
    el?.getAttribute?.('value') || '',
    el?.textContent || '',
  ].map(normalise).filter(Boolean);
  return [...new Set(labels)];
}
