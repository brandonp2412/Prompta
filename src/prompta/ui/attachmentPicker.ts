function requiredElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error("Missing required attachment UI element: " + selector);
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

function truncate(value, length = 88) {
  const text = String(value || "");
  return text.length > length
    ? text.slice(0, Math.max(1, length - 1)).trimEnd() + "…"
    : text;
}

function patchDomNode(current, next) {
  if (current.nodeType !== next.nodeType) {
    current.replaceWith(next.cloneNode(true));
    return;
  }
  if (current.nodeType === Node.TEXT_NODE) {
    if (current.textContent !== next.textContent) current.textContent = next.textContent;
    return;
  }
  if (!(current instanceof Element) || !(next instanceof Element) || current.tagName !== next.tagName) {
    current.replaceWith(next.cloneNode(true));
    return;
  }
  for (const attribute of Array.from(current.attributes)) {
    if (!next.hasAttribute(attribute.name)) current.removeAttribute(attribute.name);
  }
  for (const attribute of Array.from(next.attributes)) {
    if (current.getAttribute(attribute.name) !== attribute.value) {
      current.setAttribute(attribute.name, attribute.value);
    }
  }
  patchDomChildren(current, next);
}

function domPatchKey(node) {
  return node instanceof Element ? (node.getAttribute("data-dom-key") || "") : "";
}

function patchDomChildren(currentParent, nextParent) {
  const nextChildren = Array.from(nextParent.childNodes) as Node[];
  for (let index = 0; index < nextChildren.length; index += 1) {
    const next = nextChildren[index];
    let current = currentParent.childNodes[index];
    const nextKey = domPatchKey(next);
    if (nextKey && domPatchKey(current) !== nextKey) {
      const keyed = Array.from(currentParent.childNodes)
        .slice(index + 1)
        .find((node) => domPatchKey(node) === nextKey);
      if (keyed) {
        currentParent.insertBefore(keyed, current || null);
        current = keyed;
      }
    }
    if (!current) {
      currentParent.appendChild(next.cloneNode(true));
      continue;
    }
    patchDomNode(current, next);
  }
  while (currentParent.childNodes.length > nextChildren.length) {
    currentParent.lastChild?.remove();
  }
}

function patchHtmlChildren(element: Element, html: string) {
  const template = document.createElement("template");
  template.innerHTML = html;
  patchDomChildren(element, template.content);
}

export function createAttachmentPicker({ onChange, setStatus }) {
  const els = {
    button: requiredElement<HTMLButtonElement>("#attachmentButton"),
    menu: requiredElement<HTMLElement>("#attachmentMenu"),
    fileInput: requiredElement<HTMLInputElement>("#fileUploadInput"),
    photoInput: requiredElement<HTMLInputElement>("#photoUploadInput"),
    cameraInput: requiredElement<HTMLInputElement>("#cameraUploadInput"),
    chips: requiredElement<HTMLElement>("#attachmentChips"),
  };
  let files: File[] = [];

  function render() {
    els.chips.hidden = files.length === 0;
    patchHtmlChildren(els.chips, files.map((file, index) => (
      '<span class="attachment-chip" data-dom-key="attachment:' + index + ':' + escapeHtml(file.name) + '">'
      + '<span title="' + escapeHtml(file.name) + '">' + escapeHtml(truncate(file.name, 28)) + '</span>'
      + '<button type="button" data-remove-attachment="' + index + '" aria-label="Remove attachment">×</button>'
      + '</span>'
    )).join(""));
    onChange();
  }

  function clear() {
    files = [];
    els.fileInput.value = "";
    els.photoInput.value = "";
    els.cameraInput.value = "";
    render();
  }

  function setDisabled(disabled) {
    els.button.disabled = disabled;
    if (disabled) els.menu.hidden = true;
    for (const button of els.chips.querySelectorAll<HTMLButtonElement>("button")) {
      button.disabled = disabled;
    }
  }

  function add(nextFiles) {
    const current = [...files];
    for (const file of nextFiles) {
      if (current.length >= 5) break;
      const duplicate = current.some((existing) => (
        existing.name === file.name
        && existing.size === file.size
        && existing.lastModified === file.lastModified
      ));
      if (!duplicate) current.push(file);
    }
    files = current;
    render();
    if (nextFiles.length && current.length >= 5) {
      setStatus("Prompta supports up to 5 attachments per message.");
    }
  }

  async function payload(file) {
    if (file.size > 25 * 1024 * 1024) {
      throw new Error(file.name + " is larger than 25 MB");
    }
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(reader.error || new Error("Could not read " + file.name));
      reader.onload = () => resolve(String(reader.result || ""));
      reader.readAsDataURL(file);
    });
    const comma = dataUrl.indexOf(",");
    return {
      name: file.name,
      type: file.type || "application/octet-stream",
      data: comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl,
    };
  }

  async function serialize() {
    const total = files.reduce((sum, file) => sum + Number(file.size || 0), 0);
    if (total > 25 * 1024 * 1024) {
      throw new Error("Attachments exceed the 25 MB Prompta upload limit");
    }
    return Promise.all(files.map(payload));
  }

  function closeMenu() {
    els.menu.hidden = true;
  }

  els.button.addEventListener("click", () => {
    els.menu.hidden = !els.menu.hidden;
  });
  els.menu.addEventListener("click", (event) => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-attachment-kind]");
    if (!button) return;
    els.menu.hidden = true;
    const kind = button.dataset.attachmentKind;
    if (kind === "photo") els.photoInput.click();
    else if (kind === "camera") els.cameraInput.click();
    else els.fileInput.click();
  });
  for (const input of [els.fileInput, els.photoInput, els.cameraInput]) {
    input.addEventListener("change", () => {
      const selected = Array.from(input.files || []);
      input.value = "";
      add(selected);
    });
  }
  els.chips.addEventListener("click", (event) => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-remove-attachment]");
    if (!button) return;
    const index = Number(button.dataset.removeAttachment);
    if (!Number.isInteger(index)) return;
    files.splice(index, 1);
    render();
  });
  document.addEventListener("click", (event) => {
    const target = event.target as Node;
    if (!els.menu.hidden && !els.menu.contains(target) && !els.button.contains(target)) {
      els.menu.hidden = true;
    }
  });

  return {
    clear,
    closeMenu,
    count: () => files.length,
    serialize,
    setDisabled,
    snapshot: () => [...files],
  };
}
