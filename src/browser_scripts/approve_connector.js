(() => {
  const visible = el => el.getClientRects().length > 0;
  const label = el => {
    const copy = el.cloneNode(true);
    copy.querySelectorAll('kbd, [aria-hidden="true"]').forEach(hint => hint.remove());
    return (el.getAttribute('aria-label') || copy.textContent).trim().toLowerCase();
  };
  const buttons = [...document.querySelectorAll('button, [role="button"]')];
  for (const button of buttons) {
    if (!visible(button) || label(button) !== 'always allow') continue;
    const group = button.parentElement?.parentElement;
    if (group && [...group.querySelectorAll('button, [role="button"]')].some(el =>
      visible(el) && ['allow once', 'deny', 'decline'].includes(label(el))) &&
      !button.disabled && button.getAttribute('aria-disabled') !== 'true') {
      button.click();
      return true;
    }
  }
  for (const dialog of document.querySelectorAll('[role="dialog"], [role="alertdialog"]')) {
    if (!visible(dialog)) continue;
    const controls = [...dialog.querySelectorAll('button, [role="button"]')];
    const always = controls.find(el => visible(el) && label(el) === 'always allow');
    if (always && !always.disabled && always.getAttribute('aria-disabled') !== 'true') {
      always.click();
      return true;
    }
    const checkbox = [...dialog.querySelectorAll('input[type="checkbox"], [role="checkbox"]')]
      .find(el => visible(el) && (el.getAttribute('aria-label') || el.labels?.[0]?.textContent || el.parentElement?.textContent || '').trim().toLowerCase() === 'always allow');
    const allow = controls.find(el => visible(el) && label(el) === 'allow');
    if (checkbox && allow && !allow.disabled && allow.getAttribute('aria-disabled') !== 'true') {
      if (!(checkbox.checked || checkbox.getAttribute('aria-checked') === 'true')) checkbox.click();
      allow.click();
      return true;
    }
  }
  return false;
})()
