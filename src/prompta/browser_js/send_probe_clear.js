() => {
  const probe = window.__promptaSendProbe || {};
  if (window.__promptaSendProbeOriginalFetch) {
    window.fetch = window.__promptaSendProbeOriginalFetch;
  }
  delete window.__promptaSendProbe;
  delete window.__promptaSendProbeOriginalFetch;
  return JSON.stringify(probe);
}
