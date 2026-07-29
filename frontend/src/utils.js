/* Shared helpers: tree ops, slugs, composer pill insertion */

export function slugify(n) { return n.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }

/* Locate the children array of a dir path ("" = tree root) */
export function findChildren(arr, path) {
  if (!path) return arr;
  let cur = arr;
  for (const part of path.split("/")) {
    const n = cur.find(x => x.name === part && x.type === "dir");
    if (!n) return null;
    n.children = n.children || [];
    cur = n.children;
  }
  return cur;
}

/* Locate a single node by its full path */
export function findNode(arr, path) {
  if (!path) return null;
  const parts = path.split("/");
  const name = parts.pop();
  const children = findChildren(arr, parts.join("/"));
  return children ? children.find(x => x.name === name) || null : null;
}

/* Pick a name that doesn't collide inside the target dir */
export function uniqueName(children, base, ext) {
  let name = base + ext, i = 2;
  while (children.some(x => x.name === name)) name = `${base}-${i++}${ext}`;
  return name;
}

/* Small SVG icons for composer pills */
export const SVG_FILE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>`;
export const SVG_FOLDER = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;

/* Insert a non-editable pill at the caret of #chat-input; typing continues
   around it. DOM-based on purpose — the composer is a contenteditable. */
export function insertPill(name, isDir) {
  const input = document.getElementById("chat-input");
  if (!input) return;
  input.focus();
  const pill = document.createElement("span");
  pill.className = "pill";
  pill.contentEditable = "false";
  pill.innerHTML = `${isDir ? SVG_FOLDER : SVG_FILE}${name}<span class="x" onclick="this.parentElement.remove()">✕</span>`;
  const sel = window.getSelection();
  let range = sel.rangeCount ? sel.getRangeAt(0) : null;
  if (!range || !input.contains(range.commonAncestorContainer)) {
    range = document.createRange();
    range.selectNodeContents(input);
    range.collapse(false);
  }
  range.insertNode(pill);
  // Trailing space so the caret lands after the pill, ready for more text
  const space = document.createTextNode("\u00A0");
  pill.after(space);
  range.setStartAfter(space);
  range.collapse(true);
  sel.removeAllRanges();
  sel.addRange(range);
}
