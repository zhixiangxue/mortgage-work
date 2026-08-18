<script setup>
import { computed, ref, watch, onBeforeUnmount, defineAsyncComponent } from "vue";
import { marked } from "marked";
import { store, docs, setActiveDoc, closeTab, openTabCtx, TREE_MIME, dismissDocDiff } from "../store.js";
import { viewerSrc } from "../mocks/agent.js";
import TextEditor from "./TextEditor.vue";
import ToolMarket from "./ToolMarket.vue";
import ModelSettings from "./ModelSettings.vue";
import AgentsSettings from "./AgentsSettings.vue";
import ConvInspector from "./ConvInspector.vue";
import SettingsPane from "./SettingsPane.vue";
import LogViewer from "./LogViewer.vue";

// Lazy: pdf.js only parses when a PDF is first opened, so an engine/browser
// incompatibility inside it can break PDF preview at worst — never app boot.
const PdfViewer = defineAsyncComponent(() => import("./PdfViewer.vue"));
const WordViewer = defineAsyncComponent(() => import("./WordViewer.vue"));
const ExcelViewer = defineAsyncComponent(() => import("./ExcelViewer.vue"));

const doc = computed(() => docs[store.active]);

// ── Markdown image resolution ──
// marked renders <img src="assets/x.jpeg">, but the browser can't reach the
// local filesystem. We intercept images and load them through the pywebview
// API, swapping src for a blob: URL.
const mdImageRenderer = new marked.Renderer();
const _origImage = mdImageRenderer.image.bind(mdImageRenderer);
// marked v18+: image(token) receives a single object, not (href, title, text)
mdImageRenderer.image = function (token) {
  const result = _origImage.call(this, token);
  return result.replace("<img ", `<img data-md-src="${token.href.replace(/"/g, "&quot;")}" `);
};

// Images are uploaded to assets/ at scope root, so the path in markdown
// (e.g. assets/pasted_xxx.jpeg) is already scope-relative — no resolve needed.
async function resolveMdImages(scope) {
  if (!window.pywebview) return;
  const area = docAreaEl.value;
  if (!area) return;
  const imgs = area.querySelectorAll("img[data-md-src]");
  for (const img of imgs) {
    const src = img.getAttribute("data-md-src");
    if (!src || img.dataset.mdResolved) continue;
    img.dataset.mdResolved = "1";
    try {
      const res = await window.pywebview.api.read_file(scope, src);
      if (res && res.b64 && res.mime) {
        const bytes = Uint8Array.from(atob(res.b64), ch => ch.charCodeAt(0));
        img.src = URL.createObjectURL(new Blob([bytes], { type: res.mime }));
        img.removeAttribute("data-md-src");
      }
    } catch {
      // Leave the broken src — the browser's broken-image icon is honest feedback
    }
  }
}

function triggerResolveMdImages() {
  const f = doc.value?.file;
  if (f && f.scope) resolveMdImages(f.scope);
}

// ── Font size zoom (Ctrl/Cmd + scroll) for markdown preview #doc-area ──
// Shares the same localStorage key as TextEditor so the LO zooms once.
const FONT_SIZE_KEY = "editor-font-size";
const DEFAULT_SIZE = 12.5;
const MIN_SIZE = 10;
const MAX_SIZE = 24;

function readFontSize() {
  try {
    const v = parseFloat(localStorage.getItem(FONT_SIZE_KEY));
    return Number.isFinite(v) ? Math.max(MIN_SIZE, Math.min(MAX_SIZE, v)) : DEFAULT_SIZE;
  } catch { return DEFAULT_SIZE; }
}

const docFontSize = ref(readFontSize());
const docAreaEl = ref(null);  // template ref, set by v-else-if on the text branch

function applyDocZoom(el) {
  if (el) el.style.fontSize = docFontSize.value + "px";
}

function onDocWheel(e) {
  if (!e.ctrlKey && !e.metaKey) return;
  e.preventDefault();
  docFontSize.value = Math.max(MIN_SIZE, Math.min(MAX_SIZE,
    docFontSize.value + (e.deltaY < 0 ? 1 : -1)
  ));
  applyDocZoom(docAreaEl.value);
  try { localStorage.setItem(FONT_SIZE_KEY, String(docFontSize.value)); } catch { /* quota */ }
}

// Whenever the doc-area div materialises (tab switch, file load, edit→preview),
// apply persisted zoom, bind Ctrl+scroll, and resolve pasted images.
watch(docAreaEl, (el, _, onCleanup) => {
  if (!el) return;
  applyDocZoom(el);
  el.addEventListener("wheel", onDocWheel, { passive: false });
  onCleanup(() => el.removeEventListener("wheel", onDocWheel));
  triggerResolveMdImages();
});

onBeforeUnmount(() => clearTimeout(retryTimer));

/* --- Tab drag-to-reorder. While dragging, a brand-colored bar marks the
   exact insertion slot (left edge of the hovered tab, or its right edge past
   the midpoint); the move happens on drop. Carries only a private mime type
   — no text/plain — so letting go over the chat composer or a tree can't
   fake a pill or a file drop. --- */
const dragTab = ref(null);
const dropIdx = ref(-1);   // insertion index into store.tabs, -1 = no marker

function tabDragStart(e, t) {
  dragTab.value = t;
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("application/x-mw-tab", t);
  // Also carry file info so dropping onto the chat area inserts a pill.
  // TREE_MIME carries {scope, path} as JSON — recognised by ChatPanel onDrop.
  const d = docs[t];
  if (d && d.file && d.file.scope && d.file.path) {
    e.dataTransfer.setData("text/plain", d.label);
    e.dataTransfer.setData(TREE_MIME, JSON.stringify({ scope: d.file.scope, path: d.file.path }));
  }
}

function tabDragOver(e, t) {
  const d = dragTab.value;
  if (!d) return;
  const from = store.tabs.indexOf(d), to = store.tabs.indexOf(t);
  if (from < 0 || to < 0) return;
  // Crossing the hovered tab's midpoint decides which side we land on
  const r = e.currentTarget.getBoundingClientRect();
  const idx = to + (e.clientX > r.left + r.width / 2 ? 1 : 0);
  // Landing back beside itself is a no-op — show no line rather than lie
  dropIdx.value = (idx === from || idx === from + 1) ? -1 : idx;
}

function tabDrop() {
  const d = dragTab.value, idx = dropIdx.value;
  tabDragEnd();
  if (!d || idx < 0) return;
  const from = store.tabs.indexOf(d);
  if (from < 0) return;
  store.tabs.splice(from, 1);
  store.tabs.splice(idx > from ? idx - 1 : idx, 0, d);
  // You just carried this tab by hand — it's what you want to look at
  setActiveDoc(d);
}

function tabDragEnd() { dragTab.value = null; dropIdx.value = -1; }

/* Dragging off the strip hides the marker — dropping there does nothing,
   so showing a line would promise a move that won't happen */
function tabsLeave(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) dropIdx.value = -1;
}

// Real repo files: markdown-family renders as HTML, the rest of the text
// kinds show verbatim. .ai files are plain markdown under the hood — same
// renderer, the different badge is enough identity.
// .ai files are agent-authored knowledge docs — always read-only preview,
// never editable. .md files keep the preview/edit toggle.
const MD_EXTS = ["md", "ai"];
const isAiDoc = computed(() => doc.value?.file?.ext === "ai");
const isMarkdown = computed(() => MD_EXTS.includes(doc.value?.file?.ext));

/* ── Inline diff: when an external edit (agent, watcher) changes a file
   that's open in a tab, show a diff overlay instead of the editor. ── */
const hasDiff = computed(() => {
  const f = doc.value?.file;
  return f && f._diff && f._diff.length;
});
const diffHunks = computed(() => (doc.value?.file?._diff) || []);
const diffStats = computed(() => {
  let adds = 0, dels = 0;
  for (const h of diffHunks.value) {
    if (h.type === "add") adds++;
    else if (h.type === "del") dels++;
  }
  return { adds, dels };
});

function doDismissDiff() {
  if (store.active) dismissDocDiff(store.active);
}

// Auto-dismiss: when the LO starts typing (editor goes dirty), the diff
// has served its purpose — they're already making further changes.
watch(() => doc.value?.file?.dirty, (dirty) => {
  if (dirty && hasDiff.value) doDismissDiff();
});
const fileHtml = computed(() => {
  const f = doc.value?.file;
  if (!f || f.status !== "ready" || f.kind !== "text" || !isMarkdown.value) return "";
  return marked.parse(f.content, { gfm: true, renderer: mdImageRenderer });
});

// After markdown renders, resolve local image srcs through pywebview → blob:
watch(fileHtml, () => triggerResolveMdImages());

// md family carries a preview/edit toggle; .ai files are locked to preview.
// Other text kinds live in the editor permanently. The mode sits on the doc
// entry so it survives tab switches (but not reopen — fresh open = fresh default).
const editableText = computed(() => {
  const f = doc.value?.file;
  return f && f.status === "ready" && f.kind === "text" && !isAiDoc.value;
});
const fileMode = computed(() => (editableText.value ? doc.value.file.mode || "edit" : ""));
function setMode(m) { if (doc.value?.file) doc.value.file.mode = m; }

// Explicit-save model: surface the platform's save chord next to the dirty dot
const saveKey = /Mac/.test(navigator.platform) ? "⌘S" : "CTRL+S";

// Data-store docs embed their real browser (falkordb/rqlite viewer, qdrant
// dashboard) instead of a mock HTML body; resolve the src at render time so
// app.py's injected window.__SERVICES__ ports are picked up.
const frameSrc = computed(() => (doc.value?.frame ? viewerSrc(doc.value.frame) : null));

// Each embedded browser is a separate local process app.py spawns. There is a
// startup gap (uv + uvicorn take a few seconds to bind the port) and the
// process can be down entirely (crashed, or never started). Pointing the
// iframe straight at a dead port strands the user on the browser's native
// "connection refused" page with no way to recover. So we health-probe the
// viewer origin first and only mount the iframe once it answers, showing a
// friendly in-app state otherwise.
//   Probing '/' (a static FileResponse) confirms the viewer PROCESS is up
//   WITHOUT touching the backing DB: a reachable-but-DB-down viewer (e.g. the
//   FalkorDB SSH tunnel dropped) still loads and renders its own error banner.
const frameState = ref("checking"); // 'checking' | 'ok' | 'down' | 'off'
let retryTimer = null;
let attempts = 0;

async function probe() {
  clearTimeout(retryTimer);
  const target = frameSrc.value;
  if (!target) return; // not a framed doc; nothing to probe
  try {
    // no-cors: we only care that the connection succeeds, not the (cross-origin,
    // unreadable) body. A refused port rejects the promise.
    await fetch(target, { mode: "no-cors", cache: "no-store" });
    if (frameSrc.value === target) frameState.value = "ok";
  } catch {
    if (frameSrc.value !== target) return; // user switched docs mid-probe
    frameState.value = "down";
    // Auto-retry a bounded number of times to ride out the startup gap; after
    // that the user drives recovery with the Retry button.
    if (attempts < 8) {
      attempts += 1;
      retryTimer = setTimeout(probe, 2000);
    }
  }
}

function retry() {
  attempts = 0;
  frameState.value = "checking";
  probe();
}

// The iframe is fine for a peek, but the viewers are debug surfaces — open
// the same URL in the OS browser for a full-screen look. Goes through the
// pywebview bridge because window.open() is swallowed inside WKWebView.
function openInBrowser() {
  const url = frameSrc.value;
  if (url && window.pywebview) window.pywebview.api.open_url(url);
}

// Re-probe whenever the embedded viewer changes (tab switch / initial open).
// Watching doc.frame alongside src covers switching between two unconfigured
// viewers — src stays null for both, so the src alone never re-fires.
watch(
  () => [frameSrc.value, doc.value?.frame],
  () => {
    clearTimeout(retryTimer);
    attempts = 0;
    if (frameSrc.value) {
      frameState.value = "checking";
      probe();
    } else if (doc.value?.frame) {
      // Framed doc but no URL: app.py never configured this viewer (its
      // .env block is absent). Plate it instead of probing forever.
      frameState.value = "off";
    } else {
      frameState.value = "checking";
    }
  },
  { immediate: true }
);
</script>

<template>
  <div id="viewer" v-if="doc">
    <div id="tabs" @dragleave="tabsLeave($event)">
      <!-- Squeezed tabs ellipsize, so hover shows the full path; middle-click
           closes and right-click gets the IDE close menu -->
      <div v-for="(t, i) in store.tabs" :key="t" class="tab"
           :class="{ active: t === store.active, ghost: t === dragTab,
                     'ins-l': dropIdx === i,
                     'ins-r': dropIdx === store.tabs.length && i === store.tabs.length - 1 }"
           draggable="true"
           @dragstart="tabDragStart($event, t)"
           @dragover.prevent="tabDragOver($event, t)"
           @drop.prevent="tabDrop()"
           @dragend="tabDragEnd()"
           @click="setActiveDoc(t)"
           @contextmenu.prevent="openTabCtx($event, t)"
           @pointerup.middle="closeTab(t)"
           :data-tip="docs[t].crumb ? docs[t].crumb.join('/') : docs[t].label">
        <span class="fbadge" :class="docs[t].badge">{{ docs[t].badge.toUpperCase() }}</span>
        <span class="tlabel">{{ docs[t].label }}</span>
        <!-- VS Code convention: the dirty dot lives where the ✕ goes -->
        <span class="close" :class="{ dirty: docs[t].file && docs[t].file.dirty }"
              @click.stop="closeTab(t)">{{ docs[t].file && docs[t].file.dirty ? "●" : "✕" }}</span>
      </div>
    </div>
    <div id="breadcrumb">
      <template v-for="(c, i) in doc.crumb" :key="i">
        <span v-if="i === doc.crumb.length - 1" class="fn">{{ c }}</span>
        <template v-else>{{ c }} <span class="sep">/</span></template>
      </template>
      <!-- IDE model: dirty state + explicit save; md family can flip to a rendered view -->
      <span v-if="editableText" class="save-state" :class="{ dirty: doc.file.dirty }">
        {{ doc.file.dirty ? "● UNSAVED · " + saveKey : "SAVED" }}
      </span>
      <span v-if="editableText && isMarkdown" class="mode-seg">
        <button :class="{ on: fileMode === 'edit' }" @click="setMode('edit')">EDIT</button>
        <button :class="{ on: fileMode === 'preview' }" @click="setMode('preview')">PREVIEW</button>
      </span>
      <!-- Embedded viewers: pop the same URL out to the OS browser so the
           debug surface can be inspected full-screen -->
      <button v-if="doc.frame" class="open-ext" @click="openInBrowser">OPEN IN BROWSER ↗</button>
    </div>
    <!-- Real repo files: loading / error / pdf / image / markdown / plain text -->
    <template v-if="doc.file">
      <div v-if="doc.file.status === 'loading'" class="frame-fallback">
        <div class="fb-spin"></div>
        <span class="fb-title">{{ doc.label }}</span>
      </div>
      <div v-else-if="doc.file.status === 'error'" class="frame-fallback">
        <div class="fb-card"><div class="fb-icon"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg></div>
          <div class="fb-title">Can't open {{ doc.label }}</div>
          <div class="fb-note">{{ doc.file.message }}</div>
        </div>
      </div>
      <!-- Inline diff: agent / external edit → show changes before the LO edits -->
      <div v-else-if="hasDiff" class="diff-view-wrap">
        <div class="diff-banner">
          <span class="diff-banner-msg">Agent edited this file</span>
          <span class="diff-banner-stat">
            {{ diffStats.adds }} addition{{ diffStats.adds !== 1 ? 's' : '' }}
            &middot;
            {{ diffStats.dels }} deletion{{ diffStats.dels !== 1 ? 's' : '' }}
          </span>
          <button class="diff-dismiss" @click="doDismissDiff">Back to editor</button>
        </div>
        <div class="diff-body">
          <div v-for="(h, i) in diffHunks" :key="i" class="diff-line" :class="h.type">
            <span class="diff-pfx">{{ h.type === 'add' ? '+' : h.type === 'del' ? '-' : '' }}</span>
            <span class="diff-txt">{{ h.text || '&nbsp;' }}</span>
          </div>
        </div>
      </div>
      <div v-else-if="doc.file.kind === 'pdf'" class="file-pane">
        <PdfViewer :key="store.active" :bytes="doc.file.bytes"
                   :scope="doc.file.scope" :path="doc.file.path"
                   :target-page="doc.file.targetPage || 0"
                   :target-seq="doc.file.targetSeq || 0"
                   @saved="doc.file.bytes = $event" />
      </div>
      <div v-else-if="doc.file.kind === 'docx'" class="file-pane">
        <WordViewer :key="store.active" :bytes="doc.file.bytes"
                    :scope="doc.file.scope" :path="doc.file.path"
                    :label="doc.label" />
      </div>
      <div v-else-if="doc.file.kind === 'xlsx'" class="file-pane">
        <ExcelViewer :key="store.active" :bytes="doc.file.bytes"
                     :scope="doc.file.scope" :path="doc.file.path"
                     :label="doc.label" />
      </div>
      <div v-else-if="doc.file.kind === 'image'" id="doc-area" class="img-area">
        <img :src="doc.file.url" :alt="doc.label" />
      </div>
      <div v-else-if="!hasDiff && editableText && (!isMarkdown || fileMode === 'edit')" class="file-pane">
        <TextEditor :key="store.active" :file="doc.file" />
      </div>
      <div v-else-if="!hasDiff && doc.file.kind === 'text'" id="doc-area" ref="docAreaEl">
        <div class="md-doc md-real" v-html="fileHtml"></div>
      </div>
      <div v-else class="frame-fallback">
        <span class="fb-title">{{ doc.label }}</span>
        <span class="fb-dash">&mdash;</span>
        <span class="fb-sub">no preview</span>
      </div>
    </template>
    <!-- Doc bodies are mock HTML strings; their styles live in global.css.
         Data-store docs (doc.frame) embed the live browser via iframe, but only
         once its local process answers a health probe (see script). -->
    <template v-else-if="doc.frame">
      <iframe v-if="frameState === 'ok'" class="doc-frame" :src="frameSrc" :title="doc.label"></iframe>
      <div v-else class="frame-fallback">
        <div class="fb-card">
          <div v-if="frameState === 'checking'" class="fb-spin"></div>
          <div v-else class="fb-icon"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg></div>
          <div class="fb-title">
            {{ frameState === 'checking' ? `Connecting to ${doc.label}…`
               : frameState === 'off' ? `${doc.label} browser not configured`
               : `${doc.label} browser unavailable` }}
          </div>
          <div v-if="frameState === 'checking'" class="fb-note">
            Waiting for the local <b>{{ doc.label }}</b> viewer to come online…
          </div>
          <div v-else-if="frameState === 'off'" class="fb-note">
            This debug viewer has no data store configured in <code>.env</code>,
            so the app didn't start it. Add its entry and restart to use it.
          </div>
          <div v-else class="fb-note">
            The local <b>{{ doc.label }}</b> viewer isn't reachable at <code>{{ frameSrc }}</code>.
            It may still be starting, or its process stopped.
            <template v-if="doc.frame === 'falkordb'"><br>If the SSH tunnel to FalkorDB dropped, reopen it, then retry.</template>
          </div>
          <button v-if="frameState === 'down'" class="fb-retry" @click="retry">Retry</button>
        </div>
      </div>
    </template>
    <!-- Component-backed panes (Tool Market, model settings) — real Vue
         surfaces reading live state, not mock HTML -->
    <SettingsPane v-else-if="doc.pane === 'settings'" :initialSection="doc.initialSection || 'models'" />
    <ToolMarket v-else-if="doc.pane === 'market'" />
    <ModelSettings v-else-if="doc.pane === 'models'" />
    <AgentsSettings v-else-if="doc.pane === 'agents'" />
    <ConvInspector v-else-if="doc.pane === 'conv-inspector'" />
    <LogViewer v-else-if="doc.pane === 'console'" />
    <div v-else id="doc-area" v-html="doc.html"></div>
  </div>
  <!-- IDE-style empty state: nothing is auto-opened, hint at how to get started -->
  <div id="empty-editor" v-else>
    <div class="e-mark">MORTGAGE <span class="inv">WORK</span></div>
    <div class="e-sub">Drop the docs. The AI does the paperwork.</div>
    <div class="e-hints">
      <div class="e-hint"><span>Open a client</span><span class="e-how">click it in the sidebar</span></div>
      <div class="e-hint"><span>Open a file</span><span class="e-how">click it in the client tree</span></div>
      <div class="e-hint"><span>Add documents</span><span class="e-how">drop files onto the tree</span></div>
      <div class="e-hint"><span>Search</span><span class="e-how"><kbd>⌘</kbd><kbd>P</kbd></span></div>
    </div>
  </div>
</template>

<style scoped>
#viewer { flex: 1; display: flex; flex-direction: column; min-height: 0; }
#tabs {
  height: 36px; background: var(--bg);
  display: flex; align-items: stretch; flex-shrink: 0;
  border-bottom: 1px solid var(--border); user-select: none;
}
.tab {
  display: flex; align-items: center; gap: 8px;
  padding: 0 16px;
  font: 500 11.5px var(--mono);
  color: var(--text-4); background: var(--bg-hover);
  border-right: 1px solid var(--border); cursor: pointer;
  max-width: 220px; min-width: 0;
}
.tab.active { background: var(--bg-editor); color: var(--text); box-shadow: inset 0 2px 0 var(--brand); }
/* The tab being dragged dims in place; the insertion slot gets a bright bar */
.tab.ghost { opacity: .35; }
.tab.ins-l { box-shadow: inset 3px 0 0 var(--brand); }
.tab.ins-r { box-shadow: inset -3px 0 0 var(--brand); }
/* Long real-world filenames get ellipsized instead of blowing up the bar */
.tab .tlabel { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 0 1 auto; min-width: 0; }
.tab .fbadge, .tab .close { flex: none; }
.tab .close { font-size: 12px; opacity: 0; }
.tab:hover .close, .tab.active .close { opacity: .5; }
/* Unsaved dot is always on — it's information, not chrome */
.tab .close.dirty { opacity: 1; color: var(--brand); }
#breadcrumb {
  height: 28px; display: flex; align-items: center; gap: 8px;
  padding: 0 16px;
  font: 400 11px var(--mono); color: var(--text-4);
  background: var(--bg-editor);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0; user-select: none;
}
#breadcrumb .sep { color: var(--border-soft); }
#breadcrumb .fn { color: var(--brand); }
/* Preview / Edit segmented control, right-aligned in the breadcrumb bar */
.mode-seg { margin-left: auto; display: flex; gap: 0; border: 1px solid var(--border); border-radius: 3px; overflow: hidden; }
.mode-seg button {
  background: none; border: 0; cursor: pointer; padding: 2px 10px;
  font: 500 9px var(--mono); letter-spacing: .1em; color: var(--text-4);
}
.mode-seg button.on { background: var(--bg-hover); color: var(--brand); }
.mode-seg button:not(.on):hover { color: var(--text-2); }
/* Dirty/saved readout — pushes itself (and the toggle) to the right edge */
.save-state { margin-left: auto; font: 400 9px var(--mono); letter-spacing: .1em; color: var(--text-4); opacity: .6; }
.save-state.dirty { color: var(--brand); opacity: 1; }
.save-state + .mode-seg { margin-left: 10px; }
/* Pop-out affordance for embedded viewers, right-aligned like the mode toggle */
.open-ext {
  margin-left: auto; cursor: pointer;
  font: 500 9px var(--mono); letter-spacing: .1em; color: var(--text-4);
  background: none; border: 1px solid var(--border); border-radius: 3px; padding: 2px 10px;
}
.open-ext:hover { color: var(--brand); border-color: var(--brand); }
/* Host for absolutely-positioned panes (CodeMirror, pdf.js) */
.file-pane { flex: 1; position: relative; min-height: 0; background: var(--bg-editor); }
#doc-area { flex: 1; overflow-y: auto; background: var(--bg-editor); font-size: 12.5px; }
/* Images centered on the editor canvas, never upscaled */
.img-area { display: flex; align-items: flex-start; justify-content: center; padding: 28px; }
.img-area img { max-width: 100%; height: auto; border: 1px solid var(--border); }
/* Embedded data browsers fill the same area, borderless like a native pane */
.doc-frame { flex: 1; width: 100%; border: 0; background: var(--bg-editor); }
/* Friendly in-app state shown while a viewer is starting up or when it's down,
   in place of the browser's native connection-refused page. */
.frame-fallback {
  flex: 1; min-height: 0; background: var(--bg-editor);
  display: flex; align-items: center; justify-content: center; gap: 10px;
}
.fb-card {
  display: flex; flex-direction: column; align-items: center; text-align: center;
  gap: 12px; max-width: 440px; padding: 32px 28px;
}
.fb-icon { font-size: 26px; color: var(--amber); line-height: 1; }
.fb-title { font: 400 11px var(--mono); color: var(--text-4); letter-spacing: .04em; }
.fb-dash { color: var(--border-soft); margin: 0 2px; }
.fb-sub { font: 400 11px var(--mono); color: var(--text-4); letter-spacing: .04em; }
.fb-note { font: 400 11.5px var(--sans); color: var(--text-4); line-height: 1.7; }
.fb-note code {
  font: 400 11px var(--mono); color: var(--text-3);
  background: var(--bg-hover); border: 1px solid var(--border-soft);
  border-radius: 3px; padding: 1px 5px;
}
.fb-retry {
  margin-top: 6px; cursor: pointer;
  font: 500 11px var(--mono); color: var(--text);
  background: var(--bg-hover); border: 1px solid var(--border);
  border-radius: 4px; padding: 5px 16px;
}
.fb-retry:hover { border-color: var(--brand); color: var(--brand); }
.fb-spin {
  width: 14px; height: 14px; border-radius: 50%;
  border: 1.5px solid var(--border); border-top-color: var(--brand);
  animation: fb-rot 0.7s linear infinite; flex-shrink: 0;
}
@keyframes fb-rot { to { transform: rotate(360deg); } }
/* Empty state — dim wordmark + shortcut hints, Qoder/VS Code style */
#empty-editor {
  flex: 1; min-height: 0; background: var(--bg-editor);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  user-select: none;
}
#empty-editor .e-mark { font: 700 16px var(--mono); letter-spacing: 1px; color: var(--text-4); }
#empty-editor .e-mark .inv { background: var(--text-4); color: var(--bg-editor); padding: 0 5px; }
#empty-editor .e-sub { margin-top: 10px; font: 400 11px var(--mono); color: var(--text-4); opacity: .7; }
#empty-editor .e-hints { margin-top: 28px; display: flex; flex-direction: column; gap: 10px; }
#empty-editor .e-hint {
  display: flex; justify-content: space-between; gap: 36px; min-width: 300px;
  font: 400 11.5px var(--sans); color: var(--text-4);
}
#empty-editor .e-how { font: 400 10.5px var(--mono); color: var(--text-4); opacity: .75; }
#empty-editor kbd {
  font: 500 10px var(--mono); color: var(--text-3);
  border: 1px solid var(--border-soft); border-radius: 3px;
  padding: 1px 5px; margin-left: 4px; background: var(--bg-hover);
}

/* ── Inline diff view ── */
.diff-view-wrap {
  flex: 1; display: flex; flex-direction: column; min-height: 0;
  background: var(--bg-editor); overflow: hidden;
}
.diff-banner {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px;
  background: var(--tint-green);
  border-bottom: 1px solid color-mix(in srgb, var(--green) 30%, transparent);
  flex-shrink: 0;
}
.diff-banner-msg {
  font: 500 11.5px var(--sans); color: var(--brand);
}
.diff-banner-stat {
  font: 400 10.5px var(--mono); color: var(--green);
  margin-left: auto;
}
.diff-dismiss {
  padding: 3px 12px;
  background: color-mix(in srgb, var(--green) 12%, transparent); color: var(--brand);
  border: 1px solid var(--green); border-radius: 4px;
  cursor: pointer; font: 500 10.5px var(--sans);
  margin-left: 12px;
}
.diff-dismiss:hover { background: var(--green); color: #fff; }

.diff-body {
  flex: 1; overflow-y: auto;
  font: 400 13px / 1.75 var(--mono);
  padding: 10px 0;
}
.diff-line {
  display: flex; align-items: baseline;
  padding: 0 16px;
  border-left: 3px solid transparent;
  min-height: 22px;
}
.diff-pfx {
  width: 20px; flex-shrink: 0;
  font-weight: 700; font-size: 12px;
  text-align: center; margin-right: 6px;
}
.diff-txt { flex: 1; padding-left: 4px; }

.diff-line.ctx { color: var(--text-2); }
.diff-line.ctx .diff-pfx { color: transparent; }
.diff-line.ctx .diff-txt { color: var(--text-2); }

.diff-line.del { border-left-color: var(--red); }
.diff-line.del .diff-pfx { color: var(--red); }
.diff-line.del .diff-txt {
  background: rgba(239,68,68,.12);
  color: #fca5a5; text-decoration: line-through;
}

.diff-line.add { border-left-color: var(--green); }
.diff-line.add .diff-pfx { color: var(--green); }
.diff-line.add .diff-txt {
  background: rgba(34,197,94,.10);
  color: #86efac;
}
</style>
