(async () => {
  const visible = el => el.isConnected && el.getClientRects().length > 0 &&
    getComputedStyle(el).visibility !== 'hidden';
  const normalize = value => (value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const label = el => {
    const copy = el.cloneNode(true);
    copy.querySelectorAll('kbd, [aria-hidden="true"]').forEach(hint => hint.remove());
    const labelled = (el.getAttribute('aria-labelledby') || '').split(/\s+/)
      .map(id => document.getElementById(id)?.textContent || '').join(' ');
    return normalize(el.getAttribute('aria-label') || labelled.trim() || copy.textContent);
  };
  const enabled = el => !el.disabled && el.getAttribute('aria-disabled') !== 'true';
  const controls = root => [...root.querySelectorAll('button, [role="button"]')];
  const isAlways = el => visible(el) && label(el) === 'always allow';
  const state = window.__promptaConnectorApproval ||= new WeakMap();
  const approve = async (button, checkbox) => {
    if (!enabled(button) || (checkbox && !enabled(checkbox))) return false;
    const previous = state.get(button) || { attempts: 0, at: -Infinity };
    if (previous.attempts >= 2 || performance.now() - previous.at < 3000) return false;
    state.set(button, { attempts: previous.attempts + 1, at: performance.now() });
    if (checkbox && !(checkbox.checked || checkbox.getAttribute('aria-checked') === 'true')) {
      checkbox.click();
      if (!(checkbox.checked || checkbox.getAttribute('aria-checked') === 'true')) return 'stuck';
    }
    button.click();
    for (let i = 0; i < 5; i++) {
      await new Promise(resolve => setTimeout(resolve, 100));
      if (!visible(button)) return true;
    }
    return 'stuck';
  };
  for (const button of controls(document)) {
    if (!isAlways(button) || !enabled(button)) continue;
    // Locate the smallest permission group despite arbitrary wrapper depth.
    for (let group = button.parentElement; group && group !== document.body; group = group.parentElement) {
      if (group.matches('[role="dialog"], [role="alertdialog"]') ||
          controls(group).some(el => visible(el) && ['allow once', 'deny', 'decline'].includes(label(el)))) {
        return await approve(button);
      }
      if (group.matches('main, article, [data-message-author-role]')) break;
    }
  }
  for (const dialog of document.querySelectorAll('[role="dialog"], [role="alertdialog"]')) {
    if (!visible(dialog)) continue;
    const checkbox = [...dialog.querySelectorAll('input[type="checkbox"], [role="checkbox"]')]
      .find(el => visible(el) && normalize(el.getAttribute('aria-label') ||
        el.labels?.[0]?.textContent || el.parentElement?.textContent) === 'always allow');
    const allow = controls(dialog).find(el => visible(el) && label(el) === 'allow');
    if (checkbox && allow) return await approve(allow, checkbox);
  }
  return false;
})()
