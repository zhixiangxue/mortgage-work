<script setup>
import { computed, ref, watch, onBeforeUnmount, defineAsyncComponent } from "vue";
import { marked } from "marked";
import { store, docs, setActiveDoc, closeTab, openTabCtx } from "../store.js";
import { viewerSrc } from "../mocks/agent.js";
import TextEditor from "./TextEditor.vue";
import ToolMarket from "./ToolMarket.vue";
import ModelSettings from "./ModelSettings.vue";
import AgentsSettings from "./AgentsSettings.vue";
import ConvInspector from "./ConvInspector.vue";
import SettingsPane from "./SettingsPane.vue";

// Lazy: pdf.js only parses when a PDF is first opened, so an engine/browser
// incompatibility inside it can break PDF preview at worst — never app boot.
const PdfViewer = defineAsyncComponent(() => import("./PdfViewer.vue"));

const doc = computed(() => docs[store.active]);

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
const MD_EXTS = ["md", "ai"];
const isMarkdown = computed(() => MD_EXTS.includes(doc.value?.file?.ext));
const fileHtml = computed(() => {
  const f = doc.value?.file;
  if (!f || f.status !== "ready" || f.kind !== "text" || !isMarkdown.value) return "";
  return marked.parse(f.content, { gfm: true });
});

// md family carries a preview/edit toggle; other text kinds live in the
// editor permanently. The mode sits on the doc entry so it survives tab
// switches (but not reopen — fresh open = fresh default).
const editableText = computed(() => {
  const f = doc.value?.file;
  return f && f.status === "ready" && f.kind === "text";
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
const frameState = ref("checking"); // 'checking' | 'ok' | 'down'
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

// Re-probe whenever the embedded viewer changes (tab switch / initial open).
watch(
  frameSrc,
  () => {
    clearTimeout(retryTimer);
    attempts = 0;
    frameState.value = "checking";
    if (frameSrc.value) probe();
  },
  { immediate: true }
);

onBeforeUnmount(() => clearTimeout(retryTimer));
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
    </div>
    <!-- Real repo files: loading / error / pdf / image / markdown / plain text -->
    <template v-if="doc.file">
      <div v-if="doc.file.status === 'loading'" class="frame-fallback">
        <div class="fb-card"><div class="fb-spin"></div>
          <div class="fb-title">Opening {{ doc.label }}…</div>
        </div>
      </div>
      <div v-else-if="doc.file.status === 'error'" class="frame-fallback">
        <div class="fb-card"><div class="fb-icon"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg></div>
          <div class="fb-title">Can't open {{ doc.label }}</div>
          <div class="fb-note">{{ doc.file.message }}</div>
        </div>
      </div>
      <div v-else-if="doc.file.kind === 'pdf'" class="file-pane">
        <PdfViewer :key="store.active" :bytes="doc.file.bytes"
                   :scope="doc.file.scope" :path="doc.file.path"
                   :target-page="doc.file.targetPage || 0"
                   :target-seq="doc.file.targetSeq || 0"
                   @saved="doc.file.bytes = $event" />
      </div>
      <div v-else-if="doc.file.kind === 'image'" id="doc-area" class="img-area">
        <img :src="doc.file.url" :alt="doc.label" />
      </div>
      <div v-else-if="editableText && (!isMarkdown || fileMode === 'edit')" class="file-pane">
        <TextEditor :key="store.active" :file="doc.file" />
      </div>
      <div v-else-if="doc.file.kind === 'text'" id="doc-area">
        <div class="md-doc md-real" v-html="fileHtml"></div>
      </div>
      <div v-else class="frame-fallback">
        <div class="fb-card"><div class="fb-icon"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg></div>
          <div class="fb-title">{{ doc.label }}</div>
          <div class="fb-note">No preview for this file type — open it from Finder.</div>
        </div>
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
            {{ frameState === 'checking' ? `Connecting to ${doc.label}…` : `${doc.label} browser unavailable` }}
          </div>
          <div v-if="frameState === 'checking'" class="fb-note">
            Waiting for the local <b>{{ doc.label }}</b> viewer to come online…
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
    <SettingsPane v-else-if="doc.pane === 'settings'" />
    <ToolMarket v-else-if="doc.pane === 'market'" />
    <ModelSettings v-else-if="doc.pane === 'models'" />
    <AgentsSettings v-else-if="doc.pane === 'agents'" />
    <ConvInspector v-else-if="doc.pane === 'conv-inspector'" />
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
/* Host for absolutely-positioned panes (CodeMirror, pdf.js) */
.file-pane { flex: 1; position: relative; min-height: 0; background: var(--bg-editor); }
#doc-area { flex: 1; overflow-y: auto; background: var(--bg-editor); }
/* Images centered on the editor canvas, never upscaled */
.img-area { display: flex; align-items: flex-start; justify-content: center; padding: 28px; }
.img-area img { max-width: 100%; height: auto; border: 1px solid var(--border); }
/* Embedded data browsers fill the same area, borderless like a native pane */
.doc-frame { flex: 1; width: 100%; border: 0; background: var(--bg-editor); }
/* Friendly in-app state shown while a viewer is starting up or when it's down,
   in place of the browser's native connection-refused page. */
.frame-fallback {
  flex: 1; min-height: 0; background: var(--bg-editor);
  display: flex; align-items: center; justify-content: center;
}
.fb-card {
  display: flex; flex-direction: column; align-items: center; text-align: center;
  gap: 12px; max-width: 440px; padding: 32px 28px;
}
.fb-icon { font-size: 26px; color: var(--amber); line-height: 1; }
.fb-title { font: 600 13px var(--sans); color: var(--text); }
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
  width: 22px; height: 22px; border-radius: 50%;
  border: 2px solid var(--border); border-top-color: var(--brand);
  animation: fb-rot 0.7s linear infinite;
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
</style>
