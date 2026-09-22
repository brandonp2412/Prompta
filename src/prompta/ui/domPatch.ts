function domPatchKey(node: Node | undefined) {
  if (!(node instanceof HTMLElement)) return "";

  return node.dataset.domKey || "";
}

function patchDomNode(current: Node, next: Node) {
  if (
    current.nodeType !== next.nodeType ||
    (current instanceof Element && next instanceof Element && current.tagName !== next.tagName)
  ) {
    const replacement = next.cloneNode(true);
    const parent = current.parentNode;

    if (!parent) return current;

    parent.replaceChild(replacement, current);

    return replacement;
  }

  if (current.nodeType === Node.TEXT_NODE && next.nodeType === Node.TEXT_NODE) {
    if (current.textContent !== next.textContent) current.textContent = next.textContent;

    return current;
  }

  if (!(current instanceof Element) || !(next instanceof Element)) return current;

  for (const attribute of Array.from(current.attributes)) {
    if (!next.hasAttribute(attribute.name)) current.removeAttribute(attribute.name);
  }

  for (const attribute of Array.from(next.attributes)) {
    if (current.getAttribute(attribute.name) !== attribute.value) {
      current.setAttribute(attribute.name, attribute.value);
    }
  }

  patchDomChildren(current, next);

  return current;
}

export function patchDomChildren(currentParent: Element, nextParent: ParentNode) {
  let index = 0;

  while (index < nextParent.childNodes.length || index < currentParent.childNodes.length) {
    let current = currentParent.childNodes[index];
    const next = nextParent.childNodes[index];

    if (!next) {
      current.remove();
      continue;
    }

    if (!current) {
      currentParent.append(next.cloneNode(true));
      index += 1;
      continue;
    }

    const nextKey = domPatchKey(next);

    if (nextKey && domPatchKey(current) !== nextKey) {
      const match = Array.from(currentParent.childNodes)
        .slice(index + 1)
        .find((candidate) => domPatchKey(candidate) === nextKey);

      if (match) {
        currentParent.insertBefore(match, current);
        current = match;
      } else {
        currentParent.insertBefore(next.cloneNode(true), current);
        index += 1;
        continue;
      }
    }

    patchDomNode(current, next);
    index += 1;
  }
}

export function patchHtmlChildren(element: Element, html: string) {
  const template = document.createElement("template");
  template.innerHTML = html;
  patchDomChildren(element, template.content);
}
