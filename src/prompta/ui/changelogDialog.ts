import { patchHtmlChildren } from "./domPatch";

function requiredElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);

  if (!element) throw new Error("Missing required changelog UI element: " + selector);

  return element;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setTextIfChanged(element: Element, value) {
  const text = String(value ?? "");

  if (element.textContent !== text) element.textContent = text;
}

export function createChangelogDialog({ fetchJson, closeSidebar }) {
  const els = {
    headLabel: requiredElement<HTMLButtonElement>("#headLabel"),
    dialog: requiredElement<HTMLDialogElement>("#changelogDialog"),
    closeButton: requiredElement<HTMLButtonElement>("#closeChangelogDialog"),
    list: requiredElement<HTMLOListElement>("#changelogList"),
    status: requiredElement<HTMLElement>("#changelogDialogStatus"),
  };

  function close() {
    if (els.dialog.open) els.dialog.close();
  }

  async function open() {
    closeSidebar();

    if (!els.dialog.open) els.dialog.showModal();

    setTextIfChanged(els.status, "Loading changelog…");
    patchHtmlChildren(els.list, '<li class="changelog-empty">Loading changes…</li>');

    try {
      const payload = await fetchJson("api/changelog");
      const changes = Array.isArray(payload.changes) ? payload.changes : [];
      patchHtmlChildren(
        els.list,
        changes.length
          ? changes
              .map(
                (change) =>
                  '<li class="changelog-entry">' + escapeHtml(change?.title || "") + "</li>",
              )
              .join("")
          : '<li class="changelog-empty">No Git commit history is available.</li>',
      );
      setTextIfChanged(
        els.status,
        changes.length + " commit" + (changes.length === 1 ? "" : "s") + " · newest first",
      );
    } catch (error) {
      patchHtmlChildren(els.list, '<li class="changelog-empty">Could not load changelog.</li>');
      setTextIfChanged(
        els.status,
        "Changelog unavailable: " + String(error).replace(/^Error:\s*/, ""),
      );
    }
  }

  els.headLabel.addEventListener("click", () => void open());
  els.closeButton.addEventListener("click", close);
  els.dialog.addEventListener("click", (event) => {
    if (event.target === els.dialog) close();
  });

  return { open, close };
}
