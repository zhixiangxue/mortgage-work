/* Shared helpers: tree ops, slugs, composer pill insertion */

export function slugify(n) { return n.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }

/* Locate the children array of a dir path ("" = tree root) */
function findChildren(arr, path) {
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

/* Small SVG icons for composer pills */
export const SVG_FILE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>`;
export const SVG_FOLDER = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;
export const SVG_QUOTE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21c3-2 5-5 5-9H4V4h8v8c0 5-3 8-9 9z"/><path d="M15 21c3-2 5-5 5-9h-4V4h8v8c0 5-3 8-9 9z" transform="translate(-2 0) scale(.92)"/></svg>`;

const escapeHtml = s =>
  s.replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

/* Drop a ready-made pill at the caret of #chat-input; typing continues
   around it. DOM-based on purpose — the composer is a contenteditable. */
function placePillAtCaret(pill) {
  const input = document.getElementById("chat-input");
  if (!input) return;
  input.focus();
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

/* Canonical file identity on a pill — the same (scope, tree-path) pair the
   read_file bridge speaks. The label stays a basename for the human; the
   dataset is what the send pipeline serializes so the agent knows exactly
   which file this is, not just what it's called. */
function tagAddress(pill, addr) {
  if (!addr || !addr.scope) return;
  pill.dataset.scope = addr.scope;
  pill.dataset.path = addr.path || "";
}

export function insertPill(name, isDir, addr) {
  const pill = document.createElement("span");
  pill.className = "pill";
  pill.contentEditable = "false";
  tagAddress(pill, addr);
  if (addr && addr.scope) pill.title = addr.scope + "/" + (addr.path || "");
  pill.innerHTML = `${isDir ? SVG_FOLDER : SVG_FILE}${escapeHtml(name)}<span class="x" onclick="this.parentElement.remove()">✕</span>`;
  placePillAtCaret(pill);
}

/* Selected document text → quote pill. The label is a short glimpse (CSS
   clamps it with an ellipsis) plus a dim source-file tag, so you can see the
   provenance rides along — not just the words. The full passage and path go
   in the hover title; the machine identity in data-scope/data-path. */
export function insertQuotePill(text, addr) {
  const pill = document.createElement("span");
  pill.className = "pill quote";
  pill.contentEditable = "false";
  const from = addr && addr.scope ? addr.scope + "/" + (addr.path || "") : "";
  pill.title = from ? `${from}\n\u201C${text}\u201D` : text;
  pill.dataset.quote = text;
  tagAddress(pill, addr);
  // Hard cap keeps huge selections out of the DOM; CSS does the visual trim
  const label = text.length > 80 ? text.slice(0, 80).trimEnd() + "…" : text;
  const srcName = addr && addr.path ? addr.path.split("/").pop() : "";
  pill.innerHTML = `${SVG_QUOTE}<span class="q">${escapeHtml(label)}</span>`
    + (srcName ? `<span class="src">${escapeHtml(srcName)}</span>` : "")
    + `<span class="x" onclick="this.parentElement.remove()">✕</span>`;
  placePillAtCaret(pill);
}
