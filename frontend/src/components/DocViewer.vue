<script setup>
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { store, docs, setActiveDoc, closeTab } from "../store.js";
import { viewerSrc } from "../mocks/agent.js";

const doc = computed(() => docs[store.active]);
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
    <div id="tabs">
      <div v-for="t in store.tabs" :key="t" class="tab" :class="{ active: t === store.active }"
           @click="setActiveDoc(t)">
        <span class="fbadge" :class="docs[t].badge">{{ docs[t].badge.toUpperCase() }}</span>
        {{ docs[t].label }} <span class="close" @click.stop="closeTab(t)">✕</span>
      </div>
    </div>
    <div id="breadcrumb">
      <template v-for="(c, i) in doc.crumb" :key="i">
        <span v-if="i === doc.crumb.length - 1" class="fn">{{ c }}</span>
        <template v-else>{{ c }} <span class="sep">/</span></template>
      </template>
    </div>
    <!-- Doc bodies are mock HTML strings; their styles live in global.css.
         Data-store docs (doc.frame) embed the live browser via iframe, but only
         once its local process answers a health probe (see script). -->
    <template v-if="doc.frame">
      <iframe v-if="frameState === 'ok'" class="doc-frame" :src="frameSrc" :title="doc.label"></iframe>
      <div v-else class="frame-fallback">
        <div class="fb-card">
          <div v-if="frameState === 'checking'" class="fb-spin"></div>
          <div v-else class="fb-icon">⚠</div>
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
}
.tab.active { background: var(--bg-editor); color: var(--text); box-shadow: inset 0 2px 0 var(--brand); }
.tab .close { font-size: 12px; opacity: 0; }
.tab:hover .close, .tab.active .close { opacity: .5; }
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
#doc-area { flex: 1; overflow-y: auto; background: var(--bg-editor); }
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
.fb-icon { font-size: 26px; color: var(--warn, #d9a441); line-height: 1; }
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
