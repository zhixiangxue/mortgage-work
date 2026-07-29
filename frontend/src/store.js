/* Single global store — Vue reactive(), no Pinia. State mirrors the old
   single-file page's `state` object plus the DOM state that used to live in
   classes/innerHTML (visibility flags, status bar, toast, overlays). */
import { reactive } from "vue";
import { CLIENTS, CLOSED } from "./mocks/clients.js";
import { CLIENT_TREE, PRODUCT_TREE, freshClientTree } from "./mocks/trees.js";
import { DOCS, freshProfileDoc } from "./mocks/docs.js";
import {
  CHAT_HOME, CHAT_CLIENT, CHAT_PRODUCTS, chatFreshClient, CHAT_HISTORY, MODELS,
} from "./mocks/chat.js";
import { CHAT_AGENT } from "./mocks/agent.js";
import { slugify, findChildren, findNode, uniqueName, insertPill } from "./utils.js";

export const docs = reactive(DOCS);

const SEARCH_SUFFIX = ` <span style="color:var(--border-soft)">⌘P</span>`;

export const store = reactive({
  view: "clients",          // 'clients' | 'products' | 'agent'
  client: null,
  tabs: [],                 // docIds
  active: null,             // active docId

  clients: CLIENTS,
  closed: CLOSED,
  clientTree: CLIENT_TREE,  // the array backing the client tree right now
  productTree: PRODUCT_TREE,
  treeTitle: "SARAH-MITCHELL/",
  selectedPath: null,       // selected node path in the client tree
  dropPath: null,           // dir path currently hovered by an OS file drag ("" = root)
  renamingPath: null,       // node path currently in inline-rename mode

  chatTitle: "Assistant",
  chatHtml: "",
  historyOpen: false,
  chatHistory: CHAT_HISTORY,
  models: MODELS,
  currentModel: "gpt-4o",

  sidebarVisible: true,
  chatVisible: true,

  sbCtx: "", sbWarn: "", sbRight: "",
  sync: { cls: "ok", label: "● SYNCED · 2M AGO" },
  searchLabel: "SEARCH — CLIENTS &amp; DOCS" + SEARCH_SUFFIX,

  toast: { msg: "", show: false },
  modalOpen: false,
  hist: { open: false, title: "", rows: [], name: "" },
  ctx: { open: false, x: 0, y: 0, items: [], path: "", type: "root" },
});

/* ================= Toast / status / sync ================= */
let toastTimer = null;
export function showToast(msg) {
  store.toast.msg = msg;
  store.toast.show = true;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { store.toast.show = false; }, 2200);
}

export function setStatus(ctx, warn, right) {
  store.sbCtx = ctx;
  store.sbWarn = warn;
  store.sbRight = right;
}

let syncTimer = null;
/* Any file mutation flips the indicator; commit/push happen silently behind it */
export function touchSync() {
  store.sync = { cls: "busy", label: "● SYNCING…" };
  clearTimeout(syncTimer);
  syncTimer = setTimeout(() => { store.sync = { cls: "ok", label: "● SYNCED · JUST NOW" }; }, 1400);
}

/* Escape hatch: the indicator is clickable, but pressing it is never required */
export function syncNow() {
  touchSync();
  showToast("Everything backs up automatically — you never need to press this");
}

/* ================= Chat ================= */
export function setChat(html, title) {
  store.chatTitle = title || "Assistant";
  store.chatHtml = html;
  store.historyOpen = false;
}

export function loadHistory(i) {
  const c = CHAT_HISTORY[i];
  if (c.thread === "client") setChat(CHAT_CLIENT, c.title);
  else if (c.thread === "products") setChat(CHAT_PRODUCTS, c.title);
  else if (c.thread === "home") setChat(CHAT_HOME, c.title);
  else { store.historyOpen = false; showToast(`${c.title} (demo)`); }
}

export function newChat() {
  // Context follows whatever is focused, like a fresh IDE chat
  const ctx = store.view === "products" ? "product library"
    : store.client ? store.client.name : "all clients";
  setChat(`
    <div class="msg ai">
      <div class="bubble">New chat · context: <code class="inline">${ctx}</code>. Ask me anything, or drop a file.</div>
    </div>`, "New Chat");
  focusChat();
}

export function focusChat() {
  store.chatVisible = true;
  requestAnimationFrame(() => {
    const input = document.getElementById("chat-input");
    if (input) input.focus();
  });
}

export function setModel(m) {
  store.currentModel = m;
}

/* ================= View switching ================= */
export function switchView(view) {
  store.view = view;
  if (view === "products") {
    showViewer(["guideline"], "guideline");
    setChat(CHAT_PRODUCTS, "Product Lookup");
    setStatus("PRODUCT LIBRARY · 4 LENDERS · 9 DOCS", "INDEXING 2 DOCS", "RATE SHEET UPDATED TODAY");
    store.searchLabel = "SEARCH — PRODUCT LIBRARY" + SEARCH_SUFFIX;
  } else if (view === "agent") {
    showViewer(["ag_main"], "ag_main");
    setChat(CHAT_AGENT, "Runtime Console");
    setStatus("AGENT RUNTIME · MAIN UP", "QUEUE 3 · WORKERS 2/4 BUSY", "ALL SERVICES UP");
    store.searchLabel = "SEARCH — TRACES &amp; LOGS" + SEARCH_SUFFIX;
  } else if (store.client) {
    focusClient();
  } else {
    showWelcome();
  }
}

export function openClient(id) {
  store.client = store.clients.concat(store.closed).find(x => x.id === id);
  switchView("clients");
}

export function closeClient() {
  store.client = null;
  switchView("clients");
}

function focusClient() {
  const c = store.client;
  // Freshly created clients get a scaffolded folder instead of Sarah's demo data
  if (c.fresh) { focusFreshClient(c); return; }
  store.treeTitle = c.name.split(" ")[0].toUpperCase() + "-" + c.name.split(" ").slice(-1)[0].toUpperCase() + "/";
  store.clientTree = CLIENT_TREE;
  // IDE convention: opening a client just focuses its folder; the editor
  // stays empty until the user opens a file — the list already shows the summary
  showEmptyViewer();
  setChat(CHAT_CLIENT, c.name.split(" ")[0] + " · Income Review");
  setStatus(c.name.toUpperCase() + " · " + c.stageLbl.toUpperCase(),
            c.missing ? c.missing + " DOCS MISSING" : "",
            "1003 DRAFT READY · MISMO 3.4");
  store.searchLabel = `SEARCH — ${c.name.replace(/ .*/, "").toUpperCase()}-MITCHELL` + SEARCH_SUFFIX;
}

function focusFreshClient(c) {
  store.treeTitle = c.id.toUpperCase() + "/";
  store.clientTree = freshClientTree(c);
  // Same as regular clients: no auto-opened tabs, the tree is the entry point
  showEmptyViewer();
  setChat(chatFreshClient(c), c.name.split(" ")[0] + " · Kickoff");
  setStatus(c.name.toUpperCase() + " · NEW LEAD", "EMPTY FILE · 0 DOCS", "BACKED UP");
  store.searchLabel = `SEARCH — ${c.id.toUpperCase()}` + SEARCH_SUFFIX;
}

export function showWelcome() {
  // Home = no client focused. IDE convention: the editor stays empty —
  // the sidebar client list already carries all the triage info
  showEmptyViewer();
  setChat(CHAT_HOME, "Daily Briefing");
  setStatus("6 CLIENTS · 4 ACTIVE", "8 DOCS MISSING ACROSS 2 FILES", "~/MORTGAGEWORK");
  store.searchLabel = "SEARCH — CLIENTS &amp; DOCS" + SEARCH_SUFFIX;
}

/* ================= Viewer ================= */
export function showViewer(tabs, activeDoc) {
  store.tabs = [...tabs];
  setActiveDoc(activeDoc);
}

/* Editor with no tabs — DocViewer renders its empty-state placeholder */
function showEmptyViewer() {
  store.tabs = [];
  setActiveDoc(null);
  store.selectedPath = null;
}

export function openDoc(docId, path) {
  if (!store.tabs.includes(docId)) store.tabs.push(docId);
  setActiveDoc(docId);
  store.selectedPath = path || null;
}

export function closeTab(docId) {
  store.tabs = store.tabs.filter(t => t !== docId);
  if (!store.tabs.length) {
    // No tabs left: reset home chat/status when no client, else just go empty
    if (store.view === "clients" && !store.client) { showWelcome(); return; }
    setActiveDoc(null);
    return;
  }
  if (store.active === docId) store.active = store.tabs[store.tabs.length - 1];
  setActiveDoc(store.active);
}

export function setActiveDoc(docId) {
  store.active = docId;
}

/* ================= New client flow ================= */
export function openNewClient() { store.modalOpen = true; }
export function closeNewClient() { store.modalOpen = false; }

export function createClient({ name, phone, email, purpose, citizenship, amount, co }) {
  name = name.trim() || "Jane Doe";
  const slug = slugify(name);
  amount = amount.trim() || "$500,000";
  if (co) co = { name: co.name.trim() || "Co-Borrower", citizenship: co.citizenship };
  const c = { id: slug, name, purpose, amount, stage: "lead", stageLbl: "New Lead",
              missing: 0, touched: "just now", city: "—", fresh: true };
  store.clients.unshift(c);
  // Scaffolded PROFILE.md — the client IS this file, from day one
  docs["p_" + slug] = freshProfileDoc(slug, name, phone.trim(), email.trim(), purpose, amount, citizenship, co);
  closeNewClient();
  showToast(`Created ~/MortgageWork/clients/${slug}/`);
  touchSync();
  openClient(slug);
}

/* ================= Drop / paste upload (UI mock) ================= */
const EXT_TYPE = { pdf: "pdf", md: "md", yml: "yml", yaml: "yml", eml: "eml",
                   png: "img", jpg: "img", jpeg: "img", gif: "img", webp: "img",
                   txt: "txt", ai: "ai" };

function activeTree() {
  return store.view === "products" ? store.productTree : store.clientTree;
}

/* Add dropped/pasted file names under a dir ("" = root). Client files get the
   U (not backed up) marker, product docs go straight to background indexing. */
export function uploadFiles(dirPath, names) {
  if (!names.length) return;
  const products = store.view === "products";
  const children = findChildren(activeTree(), dirPath);
  if (!children) return;
  for (const fname of names) {
    const dot = fname.lastIndexOf(".");
    const base = dot > 0 ? fname.slice(0, dot) : fname;
    const ext = dot > 0 ? fname.slice(dot) : "";
    const node = { name: uniqueName(children, base, ext), type: EXT_TYPE[ext.slice(1).toLowerCase()] || "md" };
    if (products) node.idx = true; else node.git = "new";
    children.push(node);
  }
  // Reveal the landing spot
  if (dirPath) { const d = findNode(activeTree(), dirPath); if (d) d.open = true; }
  touchSync();
  const dest = dirPath ? dirPath + "/" : "./";
  showToast(names.length === 1
    ? `Added ${names[0]} → ${dest} · ${products ? "indexing in background" : "extraction updates PROFILE.md"} (demo)`
    : `Added ${names.length} files → ${dest} (demo)`);
}

/* Shared drag handlers. Two payloads land on the tree:
   - OS file drags (Files) → upload
   - internal node drags (TREE_MIME, set on dragstart) → move
   Internal drags also carry text/plain so the composer pill drop still works. */
export const TREE_MIME = "application/x-tree-path";

export function dragFilesOver(e, dirPath) {
  const isFiles = e.dataTransfer.types.includes("Files");
  if (!isFiles && !e.dataTransfer.types.includes(TREE_MIME)) return;
  e.preventDefault();
  e.stopPropagation();
  e.dataTransfer.dropEffect = isFiles ? "copy" : "move";
  store.dropPath = dirPath;
}

export function dragFilesLeave(dirPath) {
  if (store.dropPath === dirPath) store.dropPath = null;
}

export function dropFilesAt(e, dirPath) {
  const types = e.dataTransfer.types;
  if (!types.includes("Files") && !types.includes(TREE_MIME)) return;
  e.preventDefault();
  e.stopPropagation();
  store.dropPath = null;
  if (types.includes("Files")) uploadFiles(dirPath, [...e.dataTransfer.files].map(f => f.name));
  else moveNode(e.dataTransfer.getData(TREE_MIME), dirPath);
}

/* Move a node (file or dir) into another dir ("" = root) */
export function moveNode(srcPath, destDir) {
  if (!srcPath) return;
  const tree = activeTree();
  const srcParent = srcPath.split("/").slice(0, -1).join("/");
  if (srcPath === destDir || srcParent === destDir) return; // onto itself / already there
  if (destDir.startsWith(srcPath + "/")) {
    showToast("Can't move a folder into itself");
    return;
  }
  const from = findChildren(tree, srcParent);
  const to = findChildren(tree, destDir);
  if (!from || !to) return;
  const name = srcPath.split("/").pop();
  const i = from.findIndex(x => x.name === name);
  if (i < 0) return;
  const [node] = from.splice(i, 1);
  // Collision in the target dir → quietly rename, IDE-style suffix
  if (to.some(x => x.name === node.name)) {
    const dot = node.type === "dir" ? -1 : node.name.lastIndexOf(".");
    node.name = uniqueName(to, dot > 0 ? node.name.slice(0, dot) : node.name, dot > 0 ? node.name.slice(dot) : "");
  }
  to.push(node);
  if (destDir) { const d = findNode(tree, destDir); if (d) d.open = true; }
  // Selection follows the moved node
  if (store.selectedPath === srcPath) store.selectedPath = (destDir ? destDir + "/" : "") + node.name;
  touchSync();
  showToast(`Moved ${node.name} → ${destDir ? destDir + "/" : "./"} (demo)`);
}

/* Paste copied files into the selected dir (a selected file targets its
   parent, nothing selected targets the root) — IDE convention */
export function pasteIntoTree(e) {
  const t = e.target;
  if (t && (t.isContentEditable || /^(INPUT|TEXTAREA)$/.test(t.tagName))) return;
  if (store.modalOpen) return;
  // Only when a tree is actually on screen (client folder or product library)
  if (store.view !== "products" && !(store.view === "clients" && store.client)) return;
  const files = [...((e.clipboardData && e.clipboardData.files) || [])];
  if (!files.length) return;
  e.preventDefault();
  let dir = "";
  const p = store.selectedPath;
  if (p) {
    const n = findNode(activeTree(), p);
    if (n) dir = n.type === "dir" ? p : p.split("/").slice(0, -1).join("/");
  }
  uploadFiles(dir, files.map(f => f.name));
}

/* ================= Inline rename — IDE-style, row turns into an input ================= */
export function startRename(path) { store.renamingPath = path; }
export function cancelRename() { store.renamingPath = null; }

export function commitRename(path, newName) {
  if (store.renamingPath !== path) return; // blur after Enter/Esc already handled it
  store.renamingPath = null;
  const tree = activeTree();
  const node = findNode(tree, path);
  if (!node) return;
  const name = newName.trim();
  if (!name || name === node.name) return;
  if (name.includes("/")) { showToast("Name can't contain /"); return; }
  const parentPath = path.split("/").slice(0, -1).join("/");
  const siblings = findChildren(tree, parentPath);
  if (siblings.some(x => x !== node && x.name === name)) {
    showToast(`${name} already exists here`);
    return;
  }
  const old = node.name;
  node.name = name;
  // Selection paths are strings — keep them pointing at the renamed subtree
  const newPath = parentPath ? parentPath + "/" + name : name;
  if (store.selectedPath === path) store.selectedPath = newPath;
  else if (store.selectedPath && store.selectedPath.startsWith(path + "/"))
    store.selectedPath = newPath + store.selectedPath.slice(path.length);
  touchSync();
  showToast(`Renamed ${old} → ${name} (demo)`);
}

/* ================= File tree context menu ================= */
export function openCtxMenu(e, node) {
  const path = node ? node.path : "";
  const type = node ? node.type : "root";
  const isFile = type === "file";
  const isDir = type === "dir";
  const items = [];
  if (isFile) items.push(["open", "Open"], ["chat", "Add to Chat"], ["history", "History…"], null, ["rename", "Rename…"], ["duplicate", "Duplicate"]);
  if (isDir) items.push(["newfile", "New File…"], ["newfolder", "New Folder…"], ["chat", "Add to Chat"], ["history", "History…"], null, ["rename", "Rename…"]);
  if (!isFile && !isDir) items.push(["newfile", "New File…"], ["newfolder", "New Folder…"]);
  items.push(null, ["copypath", "Copy Path"], ["reveal", "Reveal in Finder"]);
  if (isFile || isDir) items.push(null, ["delete", "Delete"]);
  store.ctx = { open: true, x: e.clientX, y: e.clientY, items, path, type };
}

/* Right-click on the client list — one item, that's all it needs */
export function openClientListCtx(e) {
  store.ctx = { open: true, x: e.clientX, y: e.clientY, items: [["newclient", "New Client…"]], path: "", type: "clientlist" };
}

export function hideCtx() { store.ctx.open = false; }

function clientSlug() {
  return store.client ? (store.client.fresh ? store.client.id : slugify(store.client.name)) : "";
}

export function ctxAction(act) {
  hideCtx();
  const { path, type } = store.ctx;
  const tree = activeTree();
  const products = store.view === "products";
  const name = path.split("/").pop();
  const root = products ? "~/MortgageWork/products" : `~/MortgageWork/clients/${clientSlug()}`;
  const fullPath = `${root}/${path}`;
  // Dir context targets itself; file context targets its parent dir
  const dirPath = type === "dir" ? path : path.split("/").slice(0, -1).join("/");
  switch (act) {
    case "newclient":
      openNewClient();
      break;
    case "open": {
      const node = findNode(tree, path);
      if (node) node.doc ? openDoc(node.doc, path) : showToast(`${node.name} (demo)`);
      break;
    }
    case "chat":
      insertPill(name, type === "dir");
      break;
    case "history":
      openHistory(path);
      break;
    case "newfolder": {
      const children = findChildren(tree, dirPath);
      if (children) {
        const node = { name: uniqueName(children, "new-folder", ""), type: "dir", open: true, children: [] };
        children.push(node);
        revealDir(tree, dirPath);
        touchSync();
        // Straight into rename — nobody wants a folder called new-folder
        startRename(dirPath ? dirPath + "/" + node.name : node.name);
      }
      break;
    }
    case "newfile": {
      const children = findChildren(tree, dirPath);
      if (children) {
        const node = { name: uniqueName(children, "untitled", ".md"), type: "md" };
        if (products) node.idx = true; else node.git = "new";
        children.push(node);
        revealDir(tree, dirPath);
        touchSync();
        startRename(dirPath ? dirPath + "/" + node.name : node.name);
      }
      break;
    }
    case "rename":
      startRename(path);
      break;
    case "duplicate": {
      const parent = findChildren(tree, dirPath);
      const node = findNode(tree, path);
      if (parent && node) {
        const copy = JSON.parse(JSON.stringify(node));
        const dot = node.type === "dir" ? -1 : node.name.lastIndexOf(".");
        copy.name = uniqueName(parent, (dot > 0 ? node.name.slice(0, dot) : node.name) + "-copy",
                               dot > 0 ? node.name.slice(dot) : "");
        if (products) copy.idx = true; else copy.git = "new";
        parent.splice(parent.indexOf(node) + 1, 0, copy);
        touchSync();
        showToast(`Duplicated ${node.name} (demo)`);
      }
      break;
    }
    case "copypath":
      navigator.clipboard && navigator.clipboard.writeText(fullPath);
      showToast("Path copied");
      break;
    case "reveal":
      showToast(`Revealing ${path || "folder"} in Finder… (demo)`);
      break;
    case "delete": {
      const parent = findChildren(tree, dirPath === path ? path.split("/").slice(0, -1).join("/") : dirPath);
      if (parent) {
        const i = parent.findIndex(x => x.name === name);
        if (i >= 0) parent.splice(i, 1);
        touchSync();
        showToast(`Deleted ${name} · recoverable from History (demo)`);
      }
      break;
    }
  }
}

/* New nodes must be visible for the inline-rename input to focus */
function revealDir(tree, dirPath) {
  if (!dirPath) return;
  const d = findNode(tree, dirPath);
  if (d) d.open = true;
}

/* ================= File history — the LO-facing face of git log ================= */
export function openHistory(path) {
  const name = path.split("/").pop();
  // Mocked git log, translated to human language: time · who · what
  store.hist = {
    open: true,
    name,
    title: name.toUpperCase() + " — HISTORY",
    rows: [
      ["Today 2:14 PM", "AI", "Updated after july paystub landed"],
      ["Today 11:02 AM", "AI", "Rebuilt from folder contents"],
      ["Yesterday 4:38 PM", "YOU", "Added via drag & drop"],
      ["Jul 24, 9:15 AM", "AI", "Created"],
    ],
  };
}

export function closeHist() { store.hist.open = false; }

/* ================= Panels (native View menu) ================= */
export function togglePanel(id) {
  if (id === "sidebar") store.sidebarVisible = !store.sidebarVisible;
  if (id === "chat") store.chatVisible = !store.chatVisible;
}
