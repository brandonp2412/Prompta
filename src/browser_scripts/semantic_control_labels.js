el => {
  const normalise = value => String(value || '').replace(/\s+/g, ' ').trim();
  const labels = [
    el?.getAttribute?.('aria-label') || '',
    ...String(el?.getAttribute?.('aria-labelledby') || '')
      .split(/\s+/)
      .filter(Boolean)
      .map(id => document.getElementById(id)?.textContent || ''),
    ...String(el?.getAttribute?.('aria-describedby') || '')
      .split(/\s+/)
      .filter(Boolean)
      .map(id => document.getElementById(id)?.textContent || ''),
    el?.getAttribute?.('aria-roledescription') || '',
    el?.getAttribute?.('title') || '',
    el?.getAttribute?.('alt') || '',
    el?.getAttribute?.('value') || '',
    el?.textContent || '',
  ].map(normalise).filter(Boolean);
  return [...new Set(labels)];
}
