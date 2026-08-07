/* Single global store — Vue reactive(), no Pinia. State mirrors the old
   single-file page's `state` object plus the DOM state that used to live in
   classes/innerHTML (visibility flags, status bar, toast, overlays). */
import { reactive } from "vue";
import { CLIENTS, CLOSED } from "./mocks/clients.js";
import { CLIENT_TREE, PRODUCT_TREE, freshClientTree } from "./mocks/trees.js";
import { DOCS } from "./mocks/docs.js";
import { DEMO_CHAT_MESSAGES, DEMO_CONVS } from "./mocks/chat.js";
import { slugify, findNode, insertPill } from "./utils.js";

export const docs = reactive(DOCS);

export const store = reactive({
  view: "clients",          // 'clients' | 'products' | 'tools' | 'memory' | 'agent'
  client: null,
  tabs: [],                 // docIds — one shared editor strip across every view
  active: null,             // active docId

  // Workspace data starts EMPTY — the boot overlay hides the UI until the
  // real snapshot lands. Demo data only enters via loadDemoData() (plain
  // browser dev), never inside the app: mixing mock clients into a real
  // book of business invites misclicks on fake files.
  clients: [],
  closed: [],
  clientTree: [],           // the array backing the client tree right now
  productTree: [],
  demo: false,              // true only when loadDemoData() populated the store
  user: null,               // { id, name } from the backend snapshot
  repo: null,               // { path, url } of the managed work-repo clone
  bootDone: false,          // real workspace loaded (or mock fallback decided)
  bootError: "",            // repo failure shown on the boot overlay
  treeTitle: "",
  selectedPath: null,       // selected node path in the client tree
  dropPath: null,           // dir path currently hovered by an OS file drag ("" = root)
  renamingPath: null,       // node path currently in inline-rename mode
  clip: { path: "", scope: "", cut: false },   // tree clipboard (Ctrl+C / Ctrl+X)
  ask: { open: false, title: "", body: "", label: "" },  // in-app confirmation

  // One conversation, fixed on the right — switching views never replaces it.
  // Structured messages (chak dump shape), driven by chatws.js over the agent
  // WebSocket; only the user swaps it (new chat, or picking one from history).
  chat: {
    online: false,          // agent WS connected
    convId: null,           // current conversation id (chak Conversation id)
    title: "New Chat",
    context: {},            // {client?, view} the conversation was opened on
    messages: [],           // chak message dumps + optimistic local entries
    streaming: false,       // a reply is in flight — drives the stop button
    convs: [],              // history list: [{id, title, context, updated}]
  },
  historyOpen: false,

  // Models come from ~/MortgageWork/settings/models.yaml via the bridge —
  // empty until loadModels() lands, and empty forever if nothing is configured.
  // The API keys stay in Python; providers[] carries a masked hint only.
  providers: [],            // [{ provider, base_url, models, key_hint, has_key }]
  models: [],               // flat picker list: [{ ref: "openai/gpt-4o", label }]
  currentModel: null,       // a ref from models[], or null when none configured
  modelsPath: "",           // where the file lives, shown on the settings tab

  // Skills from the market repo — populated by loadSkills() on boot and after
  // every install/uninstall/toggle. Empty in plain-browser dev. A market
  // sync (clone/pull) can take seconds, so skillsLoading gates the Tool
  // Market surface to show "Opening…" instead of an empty shelf.
  skills: [],
  skillsLoading: false,     // a market sync is in flight (Tool Market open)

  // What the agent has learned from conversations, from the same models.yaml
  // via the bridge. `embedding` names the provider turning memories into
  // vectors; once anything is stored it can't change — a different model means
  // a different vector space, where nothing already written is findable.
  // `candidates` is the subset of configured providers that serve embeddings at
  // all, so the UI can explain an empty list instead of offering a dead choice.
  memory: {
    enabled: false,
    embedding: null,        // { provider, model } | null
    candidates: [],         // [{ provider, model, key_hint }]
    ready: false,           // embedding provider still configured and keyed
    memos: [],              // [{ id, content, created, modified }]
    loading: false,
    query: "",
  },

  sidebarVisible: true,
  chatVisible: true,

  sbCtx: "", sbWarn: "", sbRight: "",
  sync: { cls: "ok", label: "● SYNCED · 2M AGO" },
  indexing: { cls: "", label: "" },  // busy/failed; empty label = hidden

  toast: { msg: "", show: false },
  modalOpen: false,
  editingClient: null,      // client being edited in the modal; null = create mode
  hist: { open: false, title: "", rows: [], name: "", path: "", isDir: false },
  ctx: { open: false, x: 0, y: 0, items: [], path: "", type: "root" },
  theme: "dark",            // 'dark' | 'light' — applyTheme() is the only writer
  appMode: (typeof import.meta !== "undefined" && import.meta.env && import.meta.env.DEV) ? "dev" : "prod",
  devMode: !!(typeof import.meta !== "undefined" && import.meta.env && import.meta.env.DEV),
  _hintVersion: 0,          // bumped to force re-eval of showFolderHint after dismiss
});

/* ================= Folder hint =================
   Shown once per client when all five document buckets are still empty.
   Dismissed permanently per client via localStorage. The hint auto-hides
   once any bucket has files — no need to dismiss if the LO just starts
   using the folders. */
const FOLDER_HINT_KEY = slug => `mw-hint-folders-${slug}`;

/* True when the current client's tree is still just the five empty buckets.
   client.yaml is never shown in the tree (machine-managed), so it is filtered
   out before the count. */
export function showFolderHint() {
  // Read _hintVersion so Vue re-evaluates when dismissFolderHint bumps it;
  // localStorage itself is not reactive.
  void store._hintVersion;
  const c = store.client;
  if (!c || !c.id) return false;
  if (localStorage.getItem(FOLDER_HINT_KEY(c.id))) return false;
  const visible = (store.clientTree || []).filter(n => n.name !== "client.yaml");
  if (!visible.length) return false;
  // Every node must be an empty dir
  return visible.every(n => n.type === "dir" && !(n.children && n.children.length));
}

export function dismissFolderHint() {
  const c = store.client;
  if (c && c.id) localStorage.setItem(FOLDER_HINT_KEY(c.id), "1");
  store._hintVersion++;
}

/* The tree nodes shown to the LO — client.yaml is hidden because it is
   machine-managed (the Edit Client modal is its UI). */
export function visibleClientTree() {
  return (store.clientTree || []).filter(n => n.name !== "client.yaml");
}


/* ================= Theme =================
   The whole switch is one attribute on <html>: global.css defines every color
   twice under the same names, so flipping data-theme repaints the app. Nothing
   else in the UI branches on it — a component that needs a color asks for a
   token, which is why this stayed a ten-line feature.

   The choice is remembered in localStorage and re-applied in main.js *before*
   the app mounts, so a light-theme user never sees a black frame first. */
function applyTheme(name) {
  store.theme = name;
  document.documentElement.dataset.theme = name;
  try { localStorage.setItem("mw-theme", name); } catch { /* private mode */ }
  // Keep the OS window frame in step with the page. Best effort: the title bar
  // belongs to Windows/macOS, not to us, and older builds may just ignore it.
  if (window.pywebview?.api?.set_native_theme)
    window.pywebview.api.set_native_theme(name === "dark").catch(() => {});
}

export function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("mw-theme"); } catch { /* private mode */ }
  applyTheme(saved === "light" ? "light" : "dark");
}

export function toggleTheme() {
  applyTheme(store.theme === "dark" ? "light" : "dark");
}

export function applyAppConfig(config) {
  const mode = config && config.dev ? "dev" : "prod";
  store.appMode = mode;
  store.devMode = mode === "dev";
  if (!store.devMode && store.view === "agent") switchView("clients");
}

/* ================= Workspace hydration (real data over mocks) =================
   Inside pywebview the backend snapshot replaces the empty state above; in a
   plain browser (vite only) loadDemoData() keeps the UI browsable instead. */
export function hydrateWorkspace(snap) {
  store.demo = false;
  applySnapshot(snap);
  loadSkills();
}

/* Disk changed — a watcher push from Python, a background pull, or our own
   file operation — so rebuild everything from the new snapshot. Nothing in the
   app patches a tree by hand: this is the only way trees change, which is what
   keeps the UI from ever showing a file the checkout doesn't have.

   The session survives the swap: expanded folders, the selected row, the
   focused client, the open tabs and the chat thread all stay put. */
export function applySnapshot(snap) {
  if (!snap || snap.error) return;
  // Folder open/closed lives on the node, so carry it across by path
  const openState = {};
  for (const c of store.clients.concat(store.closed))
    if (c.tree) collectOpen(c.tree, c.id + "/", openState);
  collectOpen(store.productTree, "products/", openState);

  store.user = snap.user;
  store.repo = snap.repo;
  for (const c of snap.clients.concat(snap.closed))
    restoreOpen(c.tree || [], c.id + "/", openState, 0);
  // Lender folders open by default — the library is small, hiding it is worse
  restoreOpen(snap.productTree, "products/", openState, 1);
  store.clients = snap.clients;
  store.closed = snap.closed;
  store.productTree = snap.productTree;

  // Re-point the focused client at its new object; mock "fresh" clients only
  // exist in memory, so they're left alone.
  if (store.client && !store.client.fresh) {
    const same = snap.clients.concat(snap.closed).find(c => c.id === store.client.id);
    if (!same) {
      // Folder vanished (deleted or renamed outside the app) — don't sit on a ghost
      store.client = null;
      showWelcome();
      return;
    }
    store.client = same;
    store.clientTree = same.tree || [];
    if (store.view === "clients") clientStatus(same);
  } else if (store.view === "clients" && !store.client) {
    welcomeStatus();
  }
  // The same disk change that reshaped the tree may have rewritten a file
  // that's open in a tab — re-read those too, or the editor shows stale bytes.
  refreshOpenDocs();
}

/* Disk changed under an open tab (an agent writing to the checkout, Word
   saving over a document, a git pull) — re-read every open text file and swap
   the fresh content in. Dirty buffers are left alone: unsaved edits win until
   the user saves, same as VS Code. Content-compare keeps the no-op case free.
   Also called directly from Python when the watcher fires but the tree
   snapshot is unchanged (content-only edits leave the tree identical). */
export function refreshOpenDocs() {
  if (!window.pywebview || store.demo) return;
  for (const id of store.tabs) {
    const f = docs[id] && docs[id].file;
    if (!f || f.status !== "ready" || f.kind !== "text" || f.dirty) continue;
    window.pywebview.api.read_file(f.scope, f.path).then(res => {
      const d = docs[id];
      // Tab closed or the user started typing while we were reading — hands off
      if (!d || !d.file || d.file.dirty) return;
      if (res && !res.error && res.kind === "text" && res.content !== d.file.content)
        d.file.content = res.content;
    });
  }
}

/* Open/collapsed state of every dir, keyed by the same paths the tree renders */
function collectOpen(nodes, base, out) {
  for (const n of nodes) {
    if (n.type !== "dir") continue;
    const path = base + n.name;
    out[path] = !!n.open;
    collectOpen(n.children || [], path + "/", out);
  }
}

/* Reapply it. Folders the user never saw fall back to open until `dfltDepth`
   (products: lenders open, their subfolders closed). */
function restoreOpen(nodes, base, map, dfltDepth, depth = 0) {
  for (const n of nodes) {
    if (n.type !== "dir") continue;
    const path = base + n.name;
    n.open = path in map ? map[path] : depth < dfltDepth;
    restoreOpen(n.children || [], path + "/", map, dfltDepth, depth + 1);
  }
}

/* Plain-browser dev only: no bridge means no repo — populate the demo book
   so the UI stays browsable. Never called inside the app. */
export function loadDemoData() {
  store.demo = true;
  store.clients = CLIENTS;
  store.closed = CLOSED;
  store.clientTree = CLIENT_TREE;
  store.productTree = PRODUCT_TREE;
  // Chat mocks only when the agent service isn't reachable — with it running
  // (dev stack) the panel is already live and these would clobber a real thread
  if (!store.chat.online) {
    store.chat.title = "Daily Briefing";
    store.chat.messages = DEMO_CHAT_MESSAGES;
    store.chat.convs = DEMO_CONVS;
  }
  if (store.view === "clients" && !store.client) showWelcome();
}

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

/* Tools view status line — also re-run by ToolsPanel when a toggle flips.
   Counts come from store.skills (the real market repo data). */
export function setToolsStatus() {
  const inst = store.skills.filter(s => s.installed);
  const on = inst.filter(s => s.enabled).length;
  setStatus(`TOOLS · ${on}/${inst.length} ENABLED`, "",
            "ALL TOOLS UP");
}

/* The Tool Market opens as a regular tab in the editor area (VS Code
   extensions model): browse the shelf, install to the sidebar panel.
   Opening it triggers a market repo sync so newly-published skills appear
   without a restart — same pull-or-keep-local contract as the work repo. */
export function openToolMarket() {
  if (!docs.toolmarket) {
    docs.toolmarket = { label: "Tool Market", badge: "ai",
                        crumb: ["tools", "market"], pane: "market" };
  }
  refreshSkills();
  openDoc("toolmarket");
}

/* Install = uv sync inside the skill directory (market repo on disk).
   The backend does the real work; the button just needs a busy state while
   it runs. Returns the refreshed inventory. */
export async function installTool(s) {
  if (s.busy) return;
  s.busy = true;
  s.phase = "install";
  try {
    const res = await window.pywebview.api.install_skill(s.id);
    if (res && !res.error) {
      store.skills = res;
      showToast(`${s.name} installed`);
    } else {
      showToast((res && res.error) || `could not install ${s.name}`);
    }
  } finally {
    s.busy = false;
    s.phase = "";
  }
  setToolsStatus();
}

export async function removeTool(s) {
  if (s.busy) return;
  s.busy = true;
  try {
    const res = await window.pywebview.api.uninstall_skill(s.id);
    if (res && !res.error) {
      store.skills = res;
      showToast(`${s.name} removed`);
    } else {
      showToast((res && res.error) || `could not remove ${s.name}`);
    }
  } finally {
    s.busy = false;
  }
  setToolsStatus();
}

export async function toggleSkill(s) {
  const newVal = !s.enabled;
  s.enabled = newVal;  // optimistic
  const res = await window.pywebview.api.toggle_skill(s.id, newVal);
  if (res && !res.error) {
    store.skills = res;
  } else {
    s.enabled = !newVal;  // revert on failure
    showToast((res && res.error) || `could not toggle ${s.name}`);
  }
  setToolsStatus();
  showToast(`${s.name} ${s.enabled ? "enabled" : "disabled"}`);
}

let syncTimer = null;
/* Demo-only mutations (mock tree ops) still flip the fake indicator */
export function touchSync() {
  store.sync = { cls: "busy", label: "● SYNCING…" };
  clearTimeout(syncTimer);
  syncTimer = setTimeout(() => { store.sync = { cls: "ok", label: "● SYNCED · JUST NOW" }; }, 1400);
}

/* Ceiling for a sync round trip. Python bounds every git step it takes, so
   anything past this means the call itself never came back — show the local
   copy instead of a spinner that never stops. */
export const SYNC_TIMEOUT_MS = 30000;

/* Real sync state, pushed by the Python sync engine via evaluate_js:
   busy = commit/push in flight · ok = remote has everything ·
   offline = remote didn't answer; work is safe locally (detail = commits
   waiting to be pushed, "0" when there simply was nothing to send) */
export function setSyncState(state, detail) {
  clearTimeout(syncTimer);
  if (state === "busy") store.sync = { cls: "busy", label: "● SYNCING…" };
  else if (state === "offline") store.sync = { cls: "off", label: Number(detail) > 0
    ? `● OFFLINE · ${detail} TO PUSH` : "● OFFLINE · LOCAL COPY" };
  else store.sync = { cls: "ok", label: "● SYNCED · JUST NOW" };
  // The working tree just changed shape (edit staged, commit landed, push
  // done) — repaint the source-control colors so they never lie.
  refreshFileStatus();
}

/* Indexing state, pushed by the Python indexer via evaluate_js (same pattern
   as setSyncState). busy = RAG/KG tasks in flight; failed = at least one
   document failed (reload icon appears for manual retry); ok = all done. */
export function setIndexingState(state, detail) {
  if (state === "busy") store.indexing = { cls: "busy", label: `INDEXING ${detail}…` };
  else if (state === "failed") store.indexing = { cls: "failed", label: "INDEX FAILED" };
  else store.indexing = { cls: "", label: "" };  // ok/idle → hidden
}

/* Manual retry — fired by the reload icon in the status bar. Re-runs failed
   uploads (no task_id) and retries failed tasks (has task_id) on both RAG
   and KG sides. The backend pushes fresh state back through setIndexingState. */
export function retryIndexing() {
  if (!window.pywebview) return;
  setIndexingState("busy", "retrying");
  window.pywebview.api.retry_indexing().then(res => {
    if (res && res.error) showToast(`Retry: ${res.error}`);
  });
}

/* Paint indexing markers on product tree nodes. Called from Python via
   evaluate_js whenever the indexer's file sets change.
   ``indexingPaths`` → badge slot shows a pulsing INDEXING… chip.
   ``failedPaths``   → badge slot shows an amber FAILED chip (click to retry).
   Both are products-relative (e.g. "JMAC/Newport-Non-Conforming.pdf"). */
export function paintIndexing(indexingPaths, failedPaths) {
  const idxSet = new Set(indexingPaths || []);
  const failSet = new Set(failedPaths || []);
  function walk(nodes, base) {
    for (const n of nodes) {
      const path = base + n.name;
      if (n.type === "dir") {
        walk(n.children || [], path + "/");
      } else {
        if (failSet.has(path)) n.idx = "failed";
        else if (idxSet.has(path)) n.idx = "indexing";
        else delete n.idx;
      }
    }
  }
  walk(store.productTree, "");
}

/* ================= Source-control colors in the tree =================
   Nodes carry a `git` token ("new" → green + U, "mod" → amber + M) that the
   backend fills from `git status`; folders inherit their loudest child so a
   change stays visible while collapsed. */
const GIT_RANK = { mod: 1, new: 2 };

function paintNodes(nodes, status, base) {
  let rollup = "";
  for (const n of nodes) {
    const path = base + n.name;
    const state = n.type === "dir"
      ? paintNodes(n.children || [], status, path + "/")
      : status[path] || "";
    // Delete rather than blank it: `n.git || ''` upstream treats both the
    // same, and a missing key keeps the mock/real node shapes identical.
    if (state) n.git = state; else delete n.git;
    if ((GIT_RANK[state] || 0) > (GIT_RANK[rollup] || 0)) rollup = state;
  }
  return rollup;
}

/* Repaint from a fresh backend map. Walks every row on purpose — that pass is
   what clears the colors once the sync engine commits them away. */
export function applyFileStatus(map) {
  for (const c of store.clients.concat(store.closed))
    if (c.tree) paintNodes(c.tree, map[c.id] || {}, "");
  paintNodes(store.productTree, map.products || {}, "");
}

export function refreshFileStatus() {
  // Demo mode has no repo; its mock colors are the point, leave them alone.
  if (!window.pywebview || store.demo) return;
  window.pywebview.api.file_status().then(res => { if (res) applyFileStatus(res); });
}

/* The indicator is clickable: the manual sync. It's the retry after an offline
   boot (pull + commit + push in one go), and the "I'm closing the laptop, is
   everything up?" answer. Bounded on the Python side, but guarded here too so a
   click can never leave the bar spinning forever. */
export function syncNow() {
  if (window.pywebview) {
    setSyncState("busy");
    const guard = setTimeout(() => setSyncState("offline", "0"), SYNC_TIMEOUT_MS);
    window.pywebview.api.sync_now().then(snap => {
      clearTimeout(guard);
      if (snap && snap.error) {
        setSyncState("offline", "0");
        showToast(`Sync: ${snap.error}`);
      } else if (snap) {
        // The backend already pushed the resulting state through setSyncState;
        // all that's left is the freshly pulled tree.
        hydrateWorkspace(snap);
      }
    }).catch(() => {
      clearTimeout(guard);
      setSyncState("offline", "0");
    });
    return;
  }
  touchSync();
  showToast("Everything backs up automatically — you never need to press this");
}

/* ================= Chat ================= */
/* The conversation itself lives in chatws.js (WS protocol + demo fallback);
   the store only keeps the state and this focus helper. */
export function focusChat() {
  store.chatVisible = true;
  requestAnimationFrame(() => {
    const input = document.getElementById("chat-input");
    if (input) input.focus();
  });
}

/* ================= Model settings =================
   The yaml file is the single source of truth for both surfaces that care:
   the Settings tab (edit it) and the composer picker (pick from it). Every
   mutation is a bridge call that returns the fresh file, so the UI can't
   drift from what's on disk. API keys never make the trip — providers[]
   carries `key_hint` and nothing else. */

/* Rebuild the flat picker list from the providers we just read. */
export function applyModels(view) {
  store.modelsPath = view.path || "";
  store.providers = view.providers || [];
  // The same model name under two providers would be indistinguishable in the
  // picker (a proxy and the real endpoint, say) — those get the provider back.
  const seen = {};
  for (const p of store.providers)
    for (const m of p.models) seen[m] = (seen[m] || 0) + 1;
  store.models = store.providers.flatMap(p => p.models.map(m => ({
    ref: `${p.provider}/${m}`,
    label: seen[m] > 1 ? `${m} · ${p.provider}` : m,
  })));
  // The picked model may have just been removed — never leave a stale name in
  // the composer button pointing at config that no longer exists.
  if (!store.models.some(m => m.ref === store.currentModel))
    store.currentModel = store.models.length ? store.models[0].ref : null;
}

export function loadModels() {
  if (!window.pywebview) return Promise.resolve();
  return window.pywebview.api.read_models().then(res => {
    // A broken hand-edited yaml is worth a toast: the settings tab would
    // otherwise just look empty, as if nothing had ever been configured.
    if (res && res.error) { showToast(res.error); return; }
    if (res) applyModels(res);
  });
}

/* Skills from the market repo. Called on boot (hydrateWorkspace) and after
   every install/uninstall/toggle. No-op in plain-browser dev. */
export function loadSkills() {
  if (!window.pywebview) return;
  window.pywebview.api.list_skills().then(res => {
    if (res && !res.error) store.skills = res;
  });
}

/* Sync the market repo (git pull) and return fresh inventory. Slower than
   loadSkills (one network round-trip) — used when the user opens the Tool
   Market to pick up newly-published skills without a restart. Sets a
   loading flag so the Tool Market shows an "Opening…" state instead of an
   empty shelf while the clone/pull runs. */
export function refreshSkills() {
  if (!window.pywebview) return;
  store.skillsLoading = true;
  return window.pywebview.api.refresh_skills().then(res => {
    if (res && !res.error) store.skills = res;
  }).finally(() => {
    store.skillsLoading = false;
  });
}

/* What the composer button and status bar print. */
export function modelLabel(ref) {
  const m = store.models.find(x => x.ref === ref);
  return m ? m.label : "";
}

export function setModel(m) {
  // Accepts a ref ("openai/gpt-4o") or a bare model name — the native AI menu
  // and any hand-written call only know the latter.
  const hit = store.models.find(x => x.ref === m)
           || store.models.find(x => x.ref.split("/").slice(1).join("/") === m);
  if (hit) store.currentModel = hit.ref;
}

/* Mutations. Each resolves to { ok, error } once the file is written and the
   store rebuilt. Failures toast by default; callers that surface the error
   themselves (the settings form) pass silentError to keep it off the toast. */
function writeModels(call, okMsg, opts = {}) {
  if (!window.pywebview) {
    const error = "Model settings need the desktop app — no bridge in the browser";
    if (!opts.silentError) showToast(error);
    return Promise.resolve({ ok: false, error });
  }
  return call.then(res => {
    if (!res || res.error) {
      const error = (res && res.error) || "could not save";
      if (!opts.silentError) showToast(error);
      return { ok: false, error };
    }
    applyModels(res);
    if (okMsg) showToast(okMsg);
    return { ok: true };
  });
}

export function saveProvider({ provider, base_url, api_key, models }) {
  // The form shows save errors inline (red, in the box), so no toast here.
  return writeModels(
    window.pywebview.api.save_provider(provider, base_url, api_key, models),
    `Saved ${provider} · ${models.length} model${models.length > 1 ? "s" : ""}`,
    { silentError: true });
}

export function removeProvider(provider) {
  return writeModels(window.pywebview.api.remove_provider(provider),
                     `Removed ${provider} — its key is gone from models.yaml`);
}

export function removeModel(provider, model) {
  return writeModels(window.pywebview.api.remove_model(provider, model),
                     `Removed ${model}`);
}

/* One real round trip through chak. Resolves to the result so the card can
   show it inline — a toast alone would drop the reason a check failed. */
export function checkProvider(provider) {
  if (!window.pywebview) return Promise.resolve({ ok: false, reason: "no bridge" });
  return window.pywebview.api.check_provider(provider, "").then(res => {
    if (!res || res.error) return { ok: false, reason: (res && res.error) || "check failed" };
    return res;
  });
}

export function revealModelsFile() {
  if (!window.pywebview) return;
  window.pywebview.api.reveal_models_file();
}

/* ================= Memory =================
   What the agent has learned from LO ↔ assistant conversations. Extraction is
   an LLM guess, so the LO gets to read, correct and delete — a wrong memory
   left in place keeps steering the background agents.

   Config lives in the same models.yaml as the providers; the memos live in the
   work repo (seeka). Both arrive through the bridge. */
export function setMemoryStatus() {
  const m = store.memory;
  const right = m.embedding
    ? (m.enabled ? "LEARNING" : "PAUSED")
    : "NOT CONFIGURED";
  setStatus(`MEMORY · ${m.memos.length} MEMOR${m.memos.length === 1 ? "Y" : "IES"}`,
            "", right);
}

export function loadMemoryConfig() {
  if (!window.pywebview) return Promise.resolve();
  return window.pywebview.api.read_memory_config().then(res => {
    if (!res || res.error) { if (res && res.error) showToast(res.error); return; }
    const m = store.memory;
    m.enabled = !!res.enabled;
    m.embedding = res.embedding || null;
    m.candidates = res.candidates || [];
    m.ready = !!res.ready;
    setMemoryStatus();
  });
}

/* The bank opens as a regular tab, like the Tool Market and Settings — the
   sidebar picks a bank, the editor area shows what's in it. */
export function openMemoryBank() {
  if (!docs.memory) {
    docs.memory = { label: "Work Memory", badge: "mem",
                    crumb: ["memory", "work"], pane: "memory" };
  }
  openDoc("memory");
  loadMemos();
}

export function loadMemos() {
  if (!window.pywebview) return Promise.resolve();
  const m = store.memory;
  const q = m.query.trim();
  m.loading = true;
  // Search goes through recall() (vector similarity), so an empty query has to
  // take the other path — there is no "match everything" vector.
  const call = q ? window.pywebview.api.search_memos(q)
                 : window.pywebview.api.list_memos();
  return call.then(res => {
    if (!res || res.error) {
      if (res && res.error) showToast(res.error);
      return;
    }
    m.memos = res.memos || [];
    setMemoryStatus();
  }).finally(() => { m.loading = false; });
}

/* Picking the embedder is a one-way door while memories exist, so this is only
   reachable from the setup card (empty store). Enables in the same step: the LO
   chose a provider to turn memory on, not to fill in a form. */
export function saveMemoryEmbedding(provider, model = "") {
  if (!window.pywebview) { showToast("Memory needs the desktop app"); return Promise.resolve(); }
  return window.pywebview.api.save_memory_config(provider, model).then(res => {
    if (!res || res.error) { showToast((res && res.error) || "could not save"); return res; }
    return window.pywebview.api.set_memory_enabled(true).then(() => {
      showToast(`Memory on — embedding with ${provider}`);
      return loadMemoryConfig().then(loadMemos);
    });
  });
}

export function toggleMemory(enabled) {
  const m = store.memory;
  if (!m.embedding) { openMemoryBank(); return Promise.resolve(); }  // configure first
  if (!window.pywebview) { showToast("Memory needs the desktop app"); return Promise.resolve(); }
  const prev = m.enabled;
  m.enabled = enabled;  // optimistic
  setMemoryStatus();
  return window.pywebview.api.set_memory_enabled(enabled).then(res => {
    if (!res || res.error) {
      m.enabled = prev;
      showToast((res && res.error) || "could not change memory");
    } else {
      // Off stops learning, not remembering — say so, or "disabled" reads like
      // the pile just got thrown away.
      showToast(enabled ? "Memory on — learning from conversations"
                        : "Memory paused — nothing new will be learned");
    }
    setMemoryStatus();
  });
}

export function updateMemo(id, content) {
  if (!window.pywebview) return Promise.resolve({ ok: false });
  return window.pywebview.api.update_memo(id, content).then(res => {
    if (!res || res.error) {
      showToast((res && res.error) || "could not save that memory");
      return { ok: false };
    }
    return loadMemos().then(() => ({ ok: true }));
  });
}

/* No confirmation: one memory is re-derivable from the conversation it came
   from, unlike wiping the bank. */
export function deleteMemo(id) {
  if (!window.pywebview) return Promise.resolve();
  return window.pywebview.api.delete_memo(id).then(res => {
    if (!res || res.error) { showToast((res && res.error) || "could not delete"); return; }
    return loadMemos();
  });
}

export function forgetMemories() {
  askThen("Delete All Memories",
          "Everything the agent has learned from your conversations is deleted, "
          + "along with anything still waiting to be processed. The conversations "
          + "themselves are untouched. This can't be undone.",
          "Delete Everything",
          () => {
            if (!window.pywebview) { showToast("Memory needs the desktop app"); return; }
            window.pywebview.api.forget_memories().then(res => {
              if (!res || res.error) { showToast((res && res.error) || "could not clear memory"); return; }
              showToast("Memory cleared");
              // Reload the config too: an empty bank unlocks the embedder choice.
              loadMemoryConfig();
              loadMemos();
            });
          });
}

/* Workspace instructions (AGENTS.md) — the LO's personal rules and preferences,
   stored at the repo root. Read/written through the bridge, same as models.
   The content is injected into the chat agent's system prompt on every new
   conversation, so what the LO writes here shapes every interaction. */
export function loadAgentsMd() {
  if (!window.pywebview) return Promise.resolve({ content: "", exists: false });
  return window.pywebview.api.read_agents_md();
}

export function saveAgentsMd(content) {
  if (!window.pywebview) { showToast("Workspace instructions need the desktop app"); return Promise.resolve(); }
  return window.pywebview.api.write_agents_md(content).then(res => {
    if (res && res.error) showToast(res.error);
    return res;
  });
}

/* Settings open as a regular tab — one unified pane with a left rail that
   switches between Models & Providers and Workspace Instructions. The gear
   icon in the activity bar opens this directly: no dropdown, no two-step.
   Same "settings is just another tab" philosophy as the Tool Market. */
export function openSettings(initialSection) {
  if (!docs.settings) {
    docs.settings = { label: "Settings", badge: "set",
                      crumb: ["settings"], pane: "settings" };
  }
  if (initialSection) docs.settings.initialSection = initialSection;
  openDoc("settings");
}

/* Kept for callers that target a specific section directly (e.g. a future
   deep link). The gear itself always opens the unified pane above. */
export function openModelSettings() {
  if (!docs.modelsettings) {
    docs.modelsettings = { label: "models.yaml", badge: "yml",
                           crumb: ["settings", "models.yaml"], pane: "models" };
  }
  openDoc("modelsettings");
}

export function openAgentsSettings() {
  if (!docs.agentssettings) {
    docs.agentssettings = { label: "AGENTS.md", badge: "md",
                            crumb: ["settings", "AGENTS.md"], pane: "agents" };
  }
  openDoc("agentssettings");
}

export function openConvInspector(convId = store.chat.convId) {
  if (!store.devMode) { showToast("Conversation inspector is only available in dev mode"); return; }
  if (!convId) { showToast("No conversation open"); return; }
  if (!window.pywebview) { showToast("Conversation inspector needs the desktop app"); return; }
  const id = `conv_${String(convId).replace(/[^A-Za-z0-9_-]/g, "_")}`;
  docs[id] = {
    label: store.chat.title || "Conversation",
    badge: "ai",
    crumb: ["conversations", String(convId), "inspector"],
    pane: "conv-inspector",
    convId: String(convId),
  };
  openDoc(id);
}

/* ================= View switching =================
   The activity bar only swaps the sidebar + status. The editor is one shared
   tab strip and the chat is one fixed conversation — switching Clients /
   Products / Agent never opens or closes an editor tab and never replaces the
   chat, so what you had open (and what you were discussing) stays put. */
export function switchView(view) {
  if (view === "agent" && !store.devMode) view = "clients";
  store.view = view;
  if (view === "products") {
    const lenders = store.productTree.filter(n => n.type === "dir");
    const docs = countFiles(store.productTree);
    setStatus(`PRODUCT LIBRARY · ${lenders.length} LENDERS · ${docs} DOCS`, "", "INDEX UP TO DATE");
  } else if (view === "tools") {
    // Display/toggle cards — editor and chat stay as they were
    loadSkills();  // quick re-read (no network): picks up install/uninstall changes
    setToolsStatus();
  } else if (view === "memory") {
    loadMemoryConfig();
    setMemoryStatus();
  } else if (view === "agent") {
    const up = store.devMode ? "DEV RUNTIME" : "";
    setStatus(up, "SERVICES", "DEBUG ONLY");
  } else if (store.client) {
    focusClient();
  } else {
    showWelcome();
  }
  // Cheap (one git call) and catches changes made outside the app — files
  // dropped into the folder in Explorer, an agent writing to the checkout.
  refreshFileStatus();
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
  store.treeTitle = c.id.toUpperCase() + "/";
  // Real clients carry their folder tree in the snapshot; mocks fall back to Sarah's
  store.clientTree = c.tree || CLIENT_TREE;
  clientStatus(c);
  // Auto-open ai/profile.ai — it's the client's knowledge doc, always read-only.
  openProfileAi();
}

/* Open ai/profile.ai when one exists in the focused client's tree. Works for
   both real repo files (openRepoFile) and mock docs (openDoc). Silently skips
   when the file isn't there yet (e.g. brand-new lead with no documents). */
function openProfileAi() {
  const c = store.client;
  if (!c) return;
  const tree = store.clientTree || [];
  const aiDir = tree.find(n => n.name === "ai" && n.type === "dir");
  const node = aiDir && aiDir.children
    && aiDir.children.find(n => n.name === "profile.ai");
  if (!node) return;
  openTreeFile(node, "ai/profile.ai");
  // Tab shows the client name, not the generic filename — without this every
  // client's profile tab looks identical and you can't tell them apart.
  const docId = node.doc || `file:${c.id}:ai/profile.ai`;
  if (docs[docId]) docs[docId].label = c.name;
}

/* Status line for a focused client — split out so a rescan can refresh the
   live numbers (missing docs, stage) without disturbing the chat or the tabs. */
function clientStatus(c) {
  setStatus(c.name.toUpperCase() + " · " + c.stageLbl.toUpperCase(),
            c.broken ? "CLIENT.YAML MISSING · AI REPAIR AVAILABLE"
                     : c.missing ? c.missing + " DOCS MISSING" : "",
            store.repo ? "BACKED UP" : "1003 DRAFT READY · MISMO 3.4");
}

function focusFreshClient(c) {
  store.treeTitle = c.id.toUpperCase() + "/";
  store.clientTree = freshClientTree(c);
  // Sidebar + status only — editor strip and conversation are untouched
  setStatus(c.name.toUpperCase() + " · NEW LEAD", "EMPTY FILE · 0 DOCS", "BACKED UP");
}

export function showWelcome() {
  // Home = no client focused. Sidebar shows the client list; editor strip and
  // conversation keep whatever was there.
  welcomeStatus();
}

/* Same split as clientStatus: a rescan refreshes the counts only. */
function welcomeStatus() {
  // Counts derive from whatever is loaded — mocks before hydration, repo after
  const open = store.clients.length;
  const total = open + store.closed.length;
  const gaps = store.clients.filter(c => c.missing > 0);
  const missing = gaps.reduce((n, c) => n + c.missing, 0);
  const home = store.repo ? store.repo.path.replace(/^\/Users\/[^/]+/, "~").toUpperCase() : "~/MORTGAGEWORK";
  setStatus(`${total} CLIENTS · ${open} ACTIVE`,
            missing ? `${missing} DOCS MISSING ACROSS ${gaps.length} FILES` : "",
            home);
}

/* Files (not folders) in a tree — the number an LO reads as "docs" */
export function countFiles(nodes) {
  return nodes.reduce((n, x) => n + (x.type === "dir" ? countFiles(x.children || []) : 1), 0);
}

export function openDoc(docId, path) {
  if (!store.tabs.includes(docId)) store.tabs.push(docId);
  setActiveDoc(docId);
  store.selectedPath = path || null;
}

/* Open a file node from a tree. Mock nodes carry a doc id; real repo trees
   don't — fetch from disk. Outside pywebview (plain-browser dev) there is no
   disk, so keep the toast. Shared by the tree renderer and the product-library
   filename filter so both open files the same way. */
export function openTreeFile(n, path) {
  if (n.doc) openDoc(n.doc, path);
  else if (store.repo) openRepoFile(path);
  else showToast(`${n.name} (demo)`);
}

/* Extension → the badge/type vocabulary the tree and tabs already speak */
const EXT_TYPE = { pdf: "pdf", md: "md", yml: "yml", yaml: "yml", eml: "eml",
                   png: "img", jpg: "img", jpeg: "img", gif: "img", webp: "img",
                   txt: "txt", ai: "ai" };

/* Open a real file from the work repo. The doc entry is created on first
   open and filled asynchronously by the backend — DocViewer renders the
   loading / error / ready states off doc.file. `scope` defaults to whatever
   is focused; session restore passes it explicitly (a saved tab may belong
   to a client that isn't focused anymore). */
export function openRepoFile(path, scope, opts = {}) {
  scope = scope || (store.view === "products" ? "products" : store.client && store.client.id);
  if (!scope || !window.pywebview) return;
  const targetPage = Number(opts.page || 0) || 0;
  const docId = `file:${scope}:${path}`;
  if (!docs[docId]) {
    const name = path.split("/").pop();
    const ext = name.split(".").pop().toLowerCase();
    docs[docId] = {
      label: name,
      badge: EXT_TYPE[ext] || "md",
      crumb: [scope, ...path.split("/")],
      file: { status: "loading", ext, scope, path, targetPage },
    };
    window.pywebview.api.read_file(scope, path).then(res => {
      const d = docs[docId];
      if (!d) return; // tab closed before the payload landed
      const page = d.file && d.file.targetPage ? d.file.targetPage : targetPage;
      if (res.error) { d.file = { status: "error", ext, message: res.error }; return; }
      if (res.kind === "text") {
        // IDE model: every text file opens straight into the editor; the md
        // family can still flip to PREVIEW via the breadcrumb toggle. .ai files
        // are agent-authored — locked to preview, never editable.
        d.file = { status: "ready", kind: "text", ext, scope, path,
                   mode: ext === "ai" ? "preview" : "edit", dirty: false, content: res.content };
      } else {
        const bytes = Uint8Array.from(atob(res.b64), ch => ch.charCodeAt(0));
        if (res.mime === "application/pdf") {
          // PDFs keep raw bytes: pdf.js takes `data` directly, skipping its
          // URL-fetch layer (WKWebView is unreliable at XHR-ing blob: URLs).
          // scope/path ride along — fillable forms save back through write_pdf.
          d.file = { status: "ready", kind: "pdf", ext, scope, path, bytes, mime: res.mime, targetPage: page, targetSeq: page ? 1 : 0 };
        } else {
          // Blob URL over data: URL — dodges multi-MB attribute strings in the DOM
          const url = URL.createObjectURL(new Blob([bytes], { type: res.mime }));
          const kind = res.mime.startsWith("image/") ? "image" : "binary";
          d.file = { status: "ready", kind, ext, url, mime: res.mime };
        }
      }
    });
  } else if (targetPage && docs[docId].file) {
    docs[docId].file.targetPage = targetPage;
    docs[docId].file.targetSeq = (docs[docId].file.targetSeq || 0) + 1;
  }
  openDoc(docId, path);
}

export function openCitation(docId, page) {
  if (!docId || !window.pywebview) return;
  window.pywebview.api.resolve_citation(docId).then(res => {
    if (!res || res.error) { showToast((res && res.error) || "Citation target not found"); return; }
    openRepoFile(res.path, res.scope, { page });
  });
}

/* Explicit save (Ctrl/Cmd+S in the editor): write through to disk, keep the
   in-memory copy in sync so preview/edit toggles show the same text. */
export function saveRepoFile(scope, path, content) {
  const d = docs[`file:${scope}:${path}`];
  if (d && d.file) d.file.content = content;
  if (!window.pywebview) return Promise.resolve();
  return window.pywebview.api.write_file(scope, path, content).then(res => {
    if (res && res.error) { showToast(res.error); return; }
    if (d && d.file) d.file.dirty = false;
    // No touchSync here: the backend sync engine drives the real indicator
  });
}

/* Keystrokes land here — memory only, never disk. Keeps the preview toggle
   honest and drives the dirty indicator until an explicit save. */
export function stageRepoFile(scope, path, content) {
  const d = docs[`file:${scope}:${path}`];
  if (d && d.file) { d.file.content = content; d.file.dirty = true; }
}

export function closeTab(docId) {
  // Explicit-save model: closing a tab with unsaved edits needs a nod first,
  // because dropping the entry below discards them for good.
  const dirty = docs[docId];
  if (dirty && dirty.file && dirty.file.dirty
      && !window.confirm(`${dirty.label} has unsaved changes — close anyway?`))
    return;
  store.tabs = store.tabs.filter(t => t !== docId);
  // Repo-file docs are transient: free the blob and drop the entry so a
  // reopen fetches fresh content (the file may have changed on disk)
  const d = docs[docId];
  if (d && d.file) {
    if (d.file.url) URL.revokeObjectURL(d.file.url);
    delete docs[docId];
  }
  if (!store.tabs.length) {
    // No tabs left: drop the active doc, then reset home chat/status when no
    // client is focused (showWelcome keeps the now-empty tabs, we clear active)
    setActiveDoc(null);
    if (store.view === "clients" && !store.client) showWelcome();
    return;
  }
  if (store.active === docId) store.active = store.tabs[store.tabs.length - 1];
  setActiveDoc(store.active);
}

export function setActiveDoc(docId) {
  store.active = docId;
}

/* Batch closes route through closeTab one at a time, so every dirty file
   still gets its own keep-or-discard prompt and blob cleanup stays in one
   place. A cancelled prompt just leaves that tab open, like VS Code. */
export function closeOtherTabs(docId) {
  [...store.tabs].filter(t => t !== docId).forEach(closeTab);
}

export function closeTabsRight(docId) {
  const i = store.tabs.indexOf(docId);
  if (i > -1) store.tabs.slice(i + 1).forEach(closeTab);
}

export function closeAllTabs() {
  [...store.tabs].forEach(closeTab);
}

/* ================= Session restore =================
   What was on screen, distilled to what survives a restart: the focused
   view/client, the editor strip, and the chat conversation. Saved into
   <repo>/session.json (untracked — device state, not work product) and
   replayed on the next boot. */
export function sessionState() {
  const tabs = store.tabs.map(id => {
    if (id === "modelsettings" || id === "agentssettings" || id === "toolmarket"
        || id === "memory") return { kind: id };
    const d = docs[id];
    // Only repo files can come back from disk; mock/demo docs stay behind.
    if (d && d.file && d.file.scope) return { kind: "file", scope: d.file.scope, path: d.file.path };
    return null;
  }).filter(Boolean);
  return { view: store.view, client: (store.client && store.client.id) || null,
           tabs, active: store.active, conv: store.chat.convId || null };
}

export function restoreSession(sess) {
  if (!sess || store.demo) return;
  // Focus first: tabs and trees hang off the focused client/view.
  const all = store.clients.concat(store.closed);
  if (sess.client) store.client = all.find(c => c.id === sess.client) || null;
  switchView(["clients", "products", "tools", "memory", "agent"].includes(sess.view)
             ? sess.view : "clients");
  for (const t of sess.tabs || []) {
    if (t.kind === "modelsettings") openModelSettings();
    else if (t.kind === "agentssettings") openAgentsSettings();
    else if (t.kind === "toolmarket") openToolMarket();
    else if (t.kind === "memory") openMemoryBank();
    // A tab whose client got closed out of the book is dropped silently
    else if (t.kind === "file" && t.scope && t.path
             && (t.scope === "products" || all.some(c => c.id === t.scope)))
      openRepoFile(t.path, t.scope);
  }
  const activeId = sess.active;
  if (activeId && store.tabs.includes(activeId)) setActiveDoc(activeId);
}

/* Right-click on an editor tab: the close family every IDE ships. Entries
   that can't do anything (nothing else open, already rightmost) are dropped
   rather than greyed — a two-item menu reads faster than a five-item one. */
export function openTabCtx(e, docId) {
  const i = store.tabs.indexOf(docId);
  const items = [["tabclose", "Close"]];
  if (store.tabs.length > 1) items.push(["tabothers", "Close Others"]);
  if (i > -1 && i < store.tabs.length - 1) items.push(["tabright", "Close to the Right"]);
  if (store.tabs.length > 1) items.push(null, ["taball", "Close All"]);
  store.ctx = { open: true, x: e.clientX, y: e.clientY, items, path: docId, type: "tab" };
}

/* ================= New / Edit client flow ================= */
export function openNewClient() { store.editingClient = null; store.modalOpen = true; }
export function closeNewClient() { store.modalOpen = false; store.editingClient = null; }

/* Same modal, pre-filled from the snapshot's form-shaped `edit` block — the
   form rewrites client.yaml facts in place; the folder (slug) never changes. */
export function openEditClient(id) {
  const c = store.clients.concat(store.closed).find(x => x.id === id);
  if (!c) return;
  store.editingClient = c;
  store.modalOpen = true;
}

/* ================= Confirmation, in-app =================
   Only for the handful of actions the UI can't walk back. Deleting a file is
   not one of them (git holds it, the folder's History gets it back); deleting a
   client is — the row is gone from the list, so there's nothing left to
   right-click. Native window.confirm() looks like a browser, not like this app. */
let askAct = null;

export function askThen(title, body, label, act) {
  askAct = act;
  store.ask = { open: true, title, body, label };
}

export function closeAsk() {
  askAct = null;
  store.ask.open = false;
}

export function askOk() {
  const act = askAct;
  closeAsk();
  if (act) act();
}

export function createClient(form) {
  if (store.editingClient) { updateClient(store.editingClient.id, form); return; }
  const name = form.name.trim() || "Jane Doe";
  if (!window.pywebview || store.demo) { demoClient(form, name); return; }
  closeNewClient();
  showToast(`Creating ${slugify(name)}…`);
  window.pywebview.api.create_client({ ...form, name }).then(res => {
    if (!res || res.error) { showToast((res && res.error) || "could not create client"); return; }
    // The folder exists now; the fresh snapshot is what puts it in the list
    refreshWorkspace().then(() => {
      openClient(res.id);
      showToast(`Created clients/${res.id}/`);
    });
  });
}

function updateClient(id, form) {
  // No Jane Doe fallback here — a blank name on save would silently rename
  // a real client. Keep the modal open so the field can be fixed.
  const name = form.name.trim();
  if (!name) { showToast("Client name required"); return; }
  if (noRepo()) { closeNewClient(); return; }
  closeNewClient();
  window.pywebview.api.update_client(id, { ...form, name }).then(res => {
    if (!res || res.error) { showToast((res && res.error) || "could not update client"); return; }
    // client.yaml changed on disk; the snapshot repaints the list and header
    refreshWorkspace();
    showToast(`Updated clients/${id}/client.yaml`);
  });
}

/* Plain-browser dev: no repo to scaffold into, so the client lives in memory
   with mock content. `fresh` marks it as demo-only for applySnapshot. */
function demoClient({ phone, email, purpose, citizenship, amount, co }, name) {
  const slug = slugify(name);
  amount = amount.trim() || "$500,000";
  if (co) co = { name: co.name.trim() || "Co-Borrower", citizenship: co.citizenship };
  store.clients.unshift({ id: slug, name, purpose, amount, stage: "lead", stageLbl: "New Lead",
                          missing: 0, touched: "just now", city: "—", fresh: true });
  // Demo-only: show a client.yaml viewer doc for the freshly created client
  docs["c_" + slug] = {
    label: "client.yaml", badge: "md", crumb: [slug, "client.yaml"],
    html: `<div class="md-doc">
      <p class="dim" style="font:400 11px var(--mono)"># Machine-managed by Mortgage Work — do not edit by hand.</p>
      <h1>${name} <span class="stage lead">NEW LEAD</span></h1>
      <pre style="font:400 12px var(--mono); line-height:1.6">schema: 1
name: ${name}
purpose: ${purpose.toLowerCase().replace(/\s+/g, "_")}
stage: lead${amount ? `\namount: ${amount.replace(/[$,]/g, "")}` : ""}
borrowers:${co ? `\n  - name: ${name}\n  - name: ${co.name}` : `\n  - name: ${name}`}
created: ${new Date().toISOString().slice(0, 10)}</pre>
      <div class="ai-note"><span class="who">SYSTEM</span> · Drop documents into this folder — clerk will build <b>ai/profile.ai</b> automatically.</div>
    </div>`,
  };
  closeNewClient();
  showToast(`Created ~/MortgageWork/clients/${slug}/ (demo)`);
  touchSync();
  openClient(slug);
}

/* ================= Real file operations =================
   Every one of these is a bridge call to Python, and none of them touches a
   tree. The backend writes to disk and queues a commit; we then pull a fresh
   snapshot (the watcher would push one anyway, this just skips the debounce).
   So the tree can't claim a file the checkout doesn't have — the failure mode
   the mock era shipped with. */

/* Same ceiling as the backend: a bigger base64 payload would freeze the webview */
const MAX_UPLOAD_BYTES = 40 * 1024 * 1024;

function activeTree() {
  return store.view === "products" ? store.productTree : store.clientTree;
}

/* Which folder the operation applies to: the product library or the focused
   client. Null means there's nothing on screen to write into. */
export function scopeNow() {
  return store.view === "products" ? "products" : (store.client && store.client.id) || null;
}

/* Guard for the plain-browser dev server: no bridge, no disk. Say so instead
   of miming success — that mock is exactly what made the tree lie before. */
function noRepo() {
  if (window.pywebview && !store.demo) return false;
  showToast("Demo mode — no workspace folder to write to");
  return true;
}

/* Re-read the workspace after our own write. Resolves once the tree is live. */
export function refreshWorkspace() {
  if (!window.pywebview) return Promise.resolve();
  return window.pywebview.api.workspace_snapshot().then(snap => {
    if (snap && snap.error) { showToast(snap.error); return; }
    applySnapshot(snap);
  });
}

/* Open a folder in the current tree so a new/landed row is actually visible */
function revealDir(dirPath) {
  if (!dirPath) return;
  const d = findNode(activeTree(), dirPath);
  if (d) d.open = true;
}

/* Open tabs holding unsaved edits below `path` — rename/move/delete would
   throw those away, so they get one confirmation first (IDE behaviour). */
function confirmDiscard(scope, path) {
  const dirty = Object.keys(docs).filter(id => {
    const f = docs[id].file;
    return f && f.dirty && f.scope === scope
      && (f.path === path || String(f.path).startsWith(path + "/"));
  });
  if (!dirty.length) return true;
  return window.confirm(`${dirty.length} open file(s) have unsaved changes that will be lost — continue?`);
}

/* Drop tabs whose file just moved or vanished. No prompt: the caller already
   asked. Doc entries are transient anyway — reopening refetches from disk.
   An empty `path` means the whole scope is gone (a deleted client). */
function dropTabs(scope, path) {
  for (const id of Object.keys(docs)) {
    const f = docs[id].file;
    if (!f || f.scope !== scope) continue;
    if (path && f.path !== path && !String(f.path).startsWith(path + "/")) continue;
    store.tabs = store.tabs.filter(t => t !== id);
    if (f.url) URL.revokeObjectURL(f.url);
    delete docs[id];
  }
  if (!store.tabs.includes(store.active))
    setActiveDoc(store.tabs[store.tabs.length - 1] || null);
}

/* A webview File has no disk path (Electron's does), so dropped bytes ride
   the bridge base64'd. Add Files… takes the cheaper native route. */
function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] || "");
    r.onerror = () => reject(new Error(`Could not read ${file.name}`));
    r.readAsDataURL(file);
  });
}

/* Native file picker → copy the picked files into `dirPath` ("" = scope root).
   The OS hands back real paths, so nothing crosses the bridge as base64. */
export function addFilesAt(dirPath) {
  const scope = scopeNow();
  if (!scope || noRepo()) return;
  window.pywebview.api.add_files_dialog(scope, dirPath).then(res => {
    if (!res || res.error) { showToast((res && res.error) || "could not add files"); return; }
    if (!res.count) return;                     // dialog cancelled
    refreshWorkspace().then(() => revealDir(dirPath));
    showToast(res.count === 1 ? `Added ${res.names[0]}` : `Added ${res.count} files`);
  });
}

/* Copy dropped/pasted files into a folder ("" = the scope root) */
export async function uploadFiles(dirPath, files) {
  if (!files.length) return;
  const scope = scopeNow();
  if (!scope || noRepo()) return;
  const small = files.filter(f => f.size <= MAX_UPLOAD_BYTES);
  if (small.length < files.length)
    showToast(`Skipped ${files.length - small.length} file(s) over 40 MB`);
  if (!small.length) return;
  showToast(small.length === 1 ? `Adding ${small[0].name}…` : `Adding ${small.length} files…`);
  let payload;
  try {
    payload = await Promise.all(small.map(async f => ({ name: f.name, b64: await readAsBase64(f) })));
  } catch (err) {
    showToast(err.message);
    return;
  }
  const res = await window.pywebview.api.upload_files(scope, dirPath, payload);
  if (!res || res.error) { showToast((res && res.error) || "upload failed"); return; }
  await refreshWorkspace();
  revealDir(dirPath);
  const dest = dirPath ? dirPath + "/" : "./";
  showToast(res.count === 1 ? `Added ${res.names[0]} → ${dest}`
                            : `Added ${res.count} files → ${dest}`);
}

/* Shared drag handlers. Two payloads land on the tree:
   - OS file drags (Files) → upload
   - internal node drags (TREE_MIME, set on dragstart) → move
   Internal drags also carry text/plain so the composer pill drop still works. */
export const TREE_MIME = "application/x-tree-path";
// A whole client dragged off the client list — JSON {id, name}. Separate from
// TREE_MIME on purpose: the file tree must not offer to "move" a client row.
export const CLIENT_MIME = "application/x-client-id";

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
  if (types.includes("Files")) uploadFiles(dirPath, [...e.dataTransfer.files]);
  else moveNode(e.dataTransfer.getData(TREE_MIME), dirPath);
}

/* Move a node (file or dir) into another dir ("" = root).
   Returns whether the move was actually dispatched — a cut/paste only spends
   its clipboard entry if something happened. */
export function moveNode(srcPath, destDir) {
  if (!srcPath) return false;
  const scope = scopeNow();
  if (!scope || noRepo()) return false;
  if (srcPath === destDir) return false;                                     // onto itself
  if (srcPath.split("/").slice(0, -1).join("/") === destDir) return false;   // already there
  if (destDir.startsWith(srcPath + "/")) {
    showToast("Can't move a folder into itself");
    return false;
  }
  if (!confirmDiscard(scope, srcPath)) return false;
  window.pywebview.api.move_path(scope, srcPath, destDir).then(res => {
    if (!res || res.error) { showToast((res && res.error) || "move failed"); return; }
    dropTabs(scope, srcPath);
    refreshWorkspace().then(() => {
      revealDir(destDir);
      // Selection follows the moved row, like dragging in an IDE explorer
      if (store.selectedPath === srcPath) store.selectedPath = res.path;
    });
    showToast(`Moved ${res.path.split("/").pop()} → ${destDir ? destDir + "/" : "./"}`);
  });
  return true;
}

/* ================= Tree clipboard (Ctrl+C / Ctrl+X / Ctrl+V) =================
   Cut is just a deferred move and copy is a scoped copy, so both land on the
   same backend calls the drag & drop path uses. Same-scope only: pasting into
   another client would file a document under the wrong person, and a mis-filed
   document is worse than one extra step. */

/* Is a tree the thing the user is looking at? */
function treeOnScreen() {
  return store.view === "products" || (store.view === "clients" && !!store.client);
}

/* Where a paste lands: the selected dir, a selected file's parent, else root */
function pasteTarget() {
  const p = store.selectedPath;
  if (!p) return "";
  const n = findNode(activeTree(), p);
  if (!n) return "";
  return n.type === "dir" ? p : p.split("/").slice(0, -1).join("/");
}

export function clipNode(path, cut) {
  const scope = scopeNow();
  if (!path || !scope) return;
  store.clip = { path, scope, cut };
  showToast(`${cut ? "Cut" : "Copied"} ${path.split("/").pop()}`);
}

/* The cut row renders dimmed until the paste (or a new clipboard entry) */
export function isCut(path) {
  return store.clip.cut && store.clip.path === path && store.clip.scope === scopeNow();
}

export function pasteFromClip(dirPath) {
  const { path, scope, cut } = store.clip;
  if (!path) return;
  if (scope !== scopeNow()) {
    showToast(`${path.split("/").pop()} was copied from ${scope} — paste it there`);
    return;
  }
  if (noRepo()) return;
  if (cut) {
    // Same operation as a drag & drop; the clipboard empties only if it ran
    if (moveNode(path, dirPath)) store.clip = { path: "", scope: "", cut: false };
    return;
  }
  if (dirPath === path || dirPath.startsWith(path + "/")) {
    showToast("Can't copy a folder into itself");
    return;
  }
  window.pywebview.api.copy_path(scope, path, dirPath).then(res => {
    if (!res || res.error) { showToast((res && res.error) || "paste failed"); return; }
    refreshWorkspace().then(() => {
      revealDir(dirPath);
      store.selectedPath = res.path;
    });
    showToast(`Pasted ${res.path.split("/").pop()} → ${dirPath ? dirPath + "/" : "./"}`);
  });
}

/* Ctrl/Cmd+C and Ctrl/Cmd+X on the tree. Paste rides the native paste event
   (pasteIntoTree) so files copied in Explorer keep working through the same key. */
export function treeKeys(e) {
  if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
  const key = e.key.toLowerCase();
  if (key !== "c" && key !== "x") return;
  const t = e.target;
  if (t && (t.isContentEditable || /^(INPUT|TEXTAREA)$/.test(t.tagName))) return;
  if (store.modalOpen || store.ask.open || store.hist.open || !treeOnScreen()) return;
  // Selected text wins — copying from a document must not become a file copy
  const sel = window.getSelection();
  if (sel && !sel.isCollapsed && String(sel).trim()) return;
  if (!store.selectedPath) return;
  e.preventDefault();
  clipNode(store.selectedPath, key === "x");
}

/* Paste into the tree: files copied in the OS file manager land as uploads,
   otherwise the tree's own clipboard takes over — IDE convention either way */
export function pasteIntoTree(e) {
  const t = e.target;
  if (t && (t.isContentEditable || /^(INPUT|TEXTAREA)$/.test(t.tagName))) return;
  if (store.modalOpen || !treeOnScreen()) return;
  const files = [...((e.clipboardData && e.clipboardData.files) || [])];
  if (!files.length && !store.clip.path) return;
  e.preventDefault();
  if (files.length) uploadFiles(pasteTarget(), files);
  else pasteFromClip(pasteTarget());
}

/* ================= Inline rename — IDE-style, row turns into an input ================= */
export function startRename(path) { store.renamingPath = path; }
export function cancelRename() { store.renamingPath = null; }

export function commitRename(path, newName) {
  if (store.renamingPath !== path) return; // blur after Enter/Esc already handled it
  store.renamingPath = null;
  const node = findNode(activeTree(), path);
  if (!node) return;
  const name = newName.trim();
  if (!name || name === node.name) return;
  if (name.includes("/")) { showToast("Name can't contain /"); return; }
  const scope = scopeNow();
  if (!scope || noRepo()) return;
  if (!confirmDiscard(scope, path)) return;
  const wasOpen = store.active === `file:${scope}:${path}`;
  const isDir = node.type === "dir";
  window.pywebview.api.rename_path(scope, path, name).then(res => {
    if (!res || res.error) { showToast((res && res.error) || "rename failed"); return; }
    dropTabs(scope, path);
    refreshWorkspace().then(() => {
      // Selection paths are strings — keep them pointing at the renamed subtree
      if (store.selectedPath === path) store.selectedPath = res.path;
      else if (store.selectedPath && store.selectedPath.startsWith(path + "/"))
        store.selectedPath = res.path + store.selectedPath.slice(path.length);
      // The editor follows a renamed file, the way an IDE keeps your place
      if (wasOpen && !isDir) openRepoFile(res.path);
    });
  });
}

/* ================= File tree context menu ================= */
/* The OS file manager has two names — say the right one */
const REVEAL_LABEL = navigator.userAgent.includes("Windows")
  ? "Reveal in Explorer" : "Reveal in Finder";

export function openCtxMenu(e, node) {
  const path = node ? node.path : "";
  const type = node ? node.type : "root";
  const isFile = type === "file";
  const isDir = type === "dir";
  // Paste only shows where it would actually work — same scope, something held
  const canPaste = !!store.clip.path && store.clip.scope === scopeNow();
  const items = [];
  if (isFile) items.push(["open", "Open"], ["chat", "Add to Chat"], ["history", "History…"], null, ["rename", "Rename…"], ["duplicate", "Duplicate"], ["cut", "Cut"], ["copy", "Copy"]);
  if (isDir) items.push(["newfile", "New File…"], ["newfolder", "New Folder…"], ["addfiles", "Add Files…"], ["chat", "Add to Chat"], ["history", "History…"], null, ["rename", "Rename…"], ["duplicate", "Duplicate"], ["cut", "Cut"], ["copy", "Copy"]);
  if (!isFile && !isDir) items.push(["newfile", "New File…"], ["newfolder", "New Folder…"], ["addfiles", "Add Files…"]);
  if (canPaste && !isFile) items.push(["paste", "Paste"]);
  items.push(null, ["copypath", "Copy Path"], ["reveal", REVEAL_LABEL]);
  if (isFile || isDir) items.push(null, ["delete", "Delete"]);
  store.ctx = { open: true, x: e.clientX, y: e.clientY, items, path, type };
}

/* Right-click on the client list: a row acts on that client, blank space is
   where you make a new one — an IDE explorer reads the same way. */
export function openClientListCtx(e, clientId = "") {
  const items = clientId
    ? [["openclient", "Open"], ["editclient", "Edit Client…"], ["chatclient", "Add to Chat"],
       null, ["copypath", "Copy Path"], ["reveal", REVEAL_LABEL],
       null, ["deleteclient", "Delete Client"]]
    : [["newclient", "New Client…"]];
  store.ctx = { open: true, x: e.clientX, y: e.clientY, items, path: clientId,
                type: clientId ? "client" : "clientlist" };
}

export function hideCtx() { store.ctx.open = false; }

export function ctxAction(act) {
  hideCtx();
  const { path, type } = store.ctx;
  const tree = activeTree();
  const products = store.view === "products";
  const name = path.split("/").pop();
  // A client row acts on that client's own folder, whichever client is open;
  // everything else acts inside the tree on screen.
  const onClient = type === "client";
  const scope = onClient ? path : scopeNow();
  const rel = onClient ? "" : path;
  // Dir context targets itself; file context targets its parent dir
  const dirPath = type === "dir" ? path : path.split("/").slice(0, -1).join("/");
  const api = window.pywebview && window.pywebview.api;
  switch (act) {
    case "tabclose":
      closeTab(path);
      break;
    case "tabothers":
      closeOtherTabs(path);
      break;
    case "tabright":
      closeTabsRight(path);
      break;
    case "taball":
      closeAllTabs();
      break;
    case "newclient":
      openNewClient();
      break;
    case "openclient":
      openClient(path);
      break;
    case "editclient":
      openEditClient(path);
      break;
    case "chatclient": {
      // The whole client folder as one pill — same address the drag sets
      const c = store.clients.concat(store.closed).find(x => x.id === path);
      insertPill((c && c.name) || path, true, { scope: path, path: "" });
      break;
    }
    case "deleteclient": {
      if (noRepo()) break;
      const client = store.clients.concat(store.closed).find(c => c.id === path);
      askThen("Delete Client", `${(client && client.name) || path} and every document in `
              + `clients/${path}/ will be removed from this computer. The backup keeps `
              + `the folder as it was, but the app can't put it back for you.`,
              "Delete Client", () => {
        api.delete_client(path).then(res => {
          if (!res || res.error) { showToast((res && res.error) || "could not delete client"); return; }
          dropTabs(path, "");
          // The snapshot does the rest: a focused client that no longer has a
          // folder drops back to the welcome screen there, not here
          refreshWorkspace();
          showToast(`Deleted clients/${path}/`);
        });
      });
      break;
    }
    case "open": {
      const node = findNode(tree, path);
      if (!node) break;
      if (node.doc) openDoc(node.doc, path);      // mock docs (demo mode)
      else openRepoFile(path);
      break;
    }
    case "chat":
      // The pill shows a basename; scope + tree path keep it unambiguous
      insertPill(name, type === "dir", { scope, path: rel });
      break;
    case "history":
      openHistory(path);
      break;
    case "newfolder": {
      if (!scope || noRepo()) break;
      api.create_folder(scope, dirPath, "new-folder").then(res => {
        if (!res || res.error) { showToast((res && res.error) || "could not create folder"); return; }
        refreshWorkspace().then(() => {
          revealDir(dirPath);
          // Straight into rename — nobody wants a folder called new-folder
          startRename(res.path);
        });
      });
      break;
    }
    case "newfile": {
      if (!scope || noRepo()) break;
      api.create_file(scope, dirPath, "untitled.md").then(res => {
        if (!res || res.error) { showToast((res && res.error) || "could not create file"); return; }
        refreshWorkspace().then(() => {
          revealDir(dirPath);
          startRename(res.path);
        });
      });
      break;
    }
    case "addfiles":
      addFilesAt(dirPath);
      break;
    case "rename":
      startRename(path);
      break;
    case "cut":
    case "copy":
      clipNode(path, act === "cut");
      break;
    case "paste":
      pasteFromClip(dirPath);
      break;
    case "duplicate": {
      if (!scope || noRepo()) break;
      api.duplicate_path(scope, path).then(res => {
        if (!res || res.error) { showToast((res && res.error) || "could not duplicate"); return; }
        refreshWorkspace().then(() => { store.selectedPath = res.path; });
        showToast(`Duplicated ${name} → ${res.path.split("/").pop()}`);
      });
      break;
    }
    case "copypath": {
      // The real on-disk path, so it pastes usefully into a shell or Explorer
      const root = store.repo ? `${store.repo.path}/${products && !onClient ? "products" : "clients/" + scope}`
                              : (products && !onClient ? "~/MortgageWork/products" : `~/MortgageWork/clients/${scope}`);
      navigator.clipboard && navigator.clipboard.writeText(rel ? `${root}/${rel}` : root);
      showToast("Path copied");
      break;
    }
    case "reveal":
      if (!scope || noRepo()) break;
      api.reveal_path(scope, rel).then(res => {
        if (res && res.error) showToast(res.error);
      });
      break;
    case "delete": {
      if (!scope || noRepo()) break;
      // No prompt, like an IDE explorer: git holds what it already backed up,
      // and the toast says so. The one thing it can't return is a file created
      // and deleted inside the same debounce window.
      api.delete_path(scope, path).then(res => {
        if (!res || res.error) { showToast((res && res.error) || "could not delete"); return; }
        dropTabs(scope, path);
        if (store.selectedPath === path || (store.selectedPath || "").startsWith(path + "/"))
          store.selectedPath = null;
        refreshWorkspace();
        // Honest wording: git can bring back what it already committed
        showToast(`Deleted ${name} · recoverable from History once backed up`);
      });
      break;
    }
  }
}

/* ================= File history — the LO-facing face of git log ================= */
export function openHistory(path) {
  const name = path.split("/").pop();
  const scope = scopeNow();
  const node = findNode(activeTree(), path);
  // Open immediately with an empty table; git log lands a moment later
  store.hist = { open: true, name, path, isDir: !!node && node.type === "dir",
                 title: name.toUpperCase() + " — HISTORY", rows: [] };
  if (!scope || !window.pywebview || store.demo) {
    store.hist.rows = [["—", "—", "No workspace in demo mode", ""]];
    return;
  }
  window.pywebview.api.file_history(scope, path).then(res => {
    // The panel may have been closed (or reopened on another file) meanwhile
    if (!store.hist.open || store.hist.path !== path) return;
    if (!res || res.error) { store.hist.rows = [["—", "—", (res && res.error) || "no history", ""]]; return; }
    store.hist.rows = res.rows && res.rows.length
      ? res.rows
      : [["—", "—", "Not backed up yet — history starts at the first backup", ""]];
  });
}

/* Restore one revision. Append-only: the old content comes back as a new
   change on top, so the restore itself is versioned and undoable. */
export function restoreVersion(row) {
  const [when, , , sha] = row;
  const { path, name, isDir } = store.hist;
  const scope = scopeNow();
  if (!sha || !path || !scope || noRepo()) return;
  if (!window.confirm(`Restore ${name} to how it was on ${when}?`)) return;
  closeHist();
  window.pywebview.api.restore_version(scope, path, sha).then(res => {
    if (!res || res.error) { showToast((res && res.error) || "could not restore"); return; }
    // Drop the tab first: reopening is what reads the restored bytes off disk
    dropTabs(scope, path);
    refreshWorkspace().then(() => { if (!isDir) openRepoFile(path); });
    showToast(`Restored ${name} · ${when}`);
  });
}

export function closeHist() { store.hist.open = false; }

/* ================= Panels (native View menu) ================= */
export function togglePanel(id) {
  if (id === "sidebar") store.sidebarVisible = !store.sidebarVisible;
  if (id === "chat") store.chatVisible = !store.chatVisible;
}
