<script setup>
/* Software Update panel — the single surface for the whole update flow:
   discover → download (with live progress) → install. Python's updater.py
   owns the lifecycle; every bridge call answers with a fresh state snapshot
   and every later change arrives as a setUpdateState push, so this component
   never keeps its own copy of the truth. */
import { computed, onMounted, onUnmounted } from "vue";
import { store, closeUpdatePanel, setUpdateState, showToast } from "../store.js";

const u = computed(() => store.update);

function fmtSize(n) {
  if (!n) return "";
  const mb = n / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(0)} MB` : `${Math.round(n / 1024)} KB`;
}

/* Fire one bridge call and mirror its answer. The Python side keeps pushing
   afterwards, so this is only the immediate round-trip. */
function call(method) {
  if (!window.pywebview?.api?.[method]) return;
  window.pywebview.api[method]().then(s => s && setUpdateState(s)).catch(e => {
    showToast(`Update: ${(e && e.message) || e}`);
  });
}

function download() { call("update_download"); }
function cancel()   { call("update_cancel"); }
function install()  { call("update_install"); }
function check()    { call("update_check"); }

function onKey(e) {
  if (!store.updatePanelOpen) return;
  if (e.key === "Escape") { e.stopPropagation(); closeUpdatePanel(); }
}
onMounted(() => document.addEventListener("keydown", onKey));
onUnmounted(() => document.removeEventListener("keydown", onKey));

function overlayClick(e) {
  // Closing never stops a download — it keeps running in the background and
  // the TopBar icon keeps narrating it.
  if (e.target === e.currentTarget) closeUpdatePanel();
}
</script>

<template>
  <div id="upd-overlay" v-show="store.updatePanelOpen" @click="overlayClick">
    <div id="upd">
      <div class="u-head">
        <span>Software Update</span>
        <span class="u-close" data-tip="Close" @click="closeUpdatePanel()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.6" stroke-linecap="round">
            <path d="M6 6l12 12M18 6L6 18"/>
          </svg>
        </span>
      </div>

      <div class="u-body">
        <!-- Up to date — the panel doubles as the manual check surface -->
        <template v-if="u.state === 'idle'">
          <div class="u-title">You're up to date</div>
          <div class="u-sub">Mortgage Work v{{ u.current || "…" }} is the latest build.</div>
        </template>

        <!-- New build discovered -->
        <template v-else-if="u.state === 'available'">
          <div class="u-title">Version {{ u.version }} is available</div>
          <div class="u-sub" v-if="u.size">{{ fmtSize(u.size) }} download ·
            the app keeps working while it downloads</div>
          <div class="u-notes" v-if="u.notes">{{ u.notes }}</div>
        </template>

        <!-- Background download, live progress -->
        <template v-else-if="u.state === 'downloading'">
          <div class="u-title">Downloading v{{ u.version }}…</div>
          <div class="u-bar"><div class="u-fill" :style="{ width: (u.progress || 0) + '%' }"></div></div>
          <div class="u-sub">{{ Math.floor(u.progress || 0) }}% — safe to close this panel</div>
        </template>

        <!-- Downloaded + verified, waiting for the user's word -->
        <template v-else-if="u.state === 'ready'">
          <div class="u-title">Version {{ u.version }} is ready</div>
          <div class="u-sub">Installing restarts the app — your work is saved
            automatically before it closes.</div>
          <div class="u-notes" v-if="u.notes">{{ u.notes }}</div>
        </template>

        <template v-else-if="u.state === 'installing'">
          <div class="u-title">Installing…</div>
          <div class="u-sub">The app will restart in a moment.</div>
        </template>

        <!-- Any failure keeps the release info, so retry is one click -->
        <template v-else-if="u.state === 'error'">
          <div class="u-title err">Something needs attention</div>
          <div class="u-sub">{{ u.error || "The update couldn't continue." }}</div>
        </template>
      </div>

      <div class="u-foot">
        <span class="u-ver" v-if="u.current">v{{ u.current }}
          <template v-if="u.version"> → v{{ u.version }}</template></span>
        <span class="grow"></span>
        <button class="btn-sm" @click="closeUpdatePanel()">
          {{ u.state === 'downloading' ? 'Hide' : 'Close' }}</button>
        <button class="btn-sm" v-if="u.state === 'idle'" @click="check">Check now</button>
        <button class="btn-sm" v-if="u.state === 'available'" @click="download">Download</button>
        <button class="btn-sm" v-if="u.state === 'downloading'" @click="cancel">Cancel</button>
        <button class="btn-sm primary" v-if="u.state === 'ready'" @click="install">Install now</button>
        <button class="btn-sm primary" v-if="u.state === 'error' && u.version" @click="download">Retry</button>
        <button class="btn-sm" v-if="u.state === 'error' && !u.version" @click="check">Check now</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
#upd-overlay {
  position: fixed; inset: 0; background: var(--scrim); z-index: 400;
  display: flex; align-items: center; justify-content: center;
}
#upd { width: 440px; max-width: calc(100vw - 48px);
  background: var(--bg-panel); border: 1px solid var(--border-soft); }
.u-head {
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  font: 700 10px var(--mono); letter-spacing: 2px; text-transform: uppercase;
  display: flex; align-items: center; justify-content: space-between;
}
.u-close { cursor: pointer; color: var(--text-4); display: flex; }
.u-close:hover { color: var(--text); }
.u-close svg { width: 13px; height: 13px; }
.u-body { padding: 18px 16px 14px; min-height: 96px; }
.u-title { font: 600 13px var(--sans); color: var(--text); margin-bottom: 6px; }
.u-title.err { color: var(--red); }
.u-sub { font: 400 11px var(--mono); color: var(--text-3); line-height: 1.6; }
.u-notes {
  margin-top: 12px; padding: 10px 12px;
  background: var(--bg); border: 1px solid var(--border);
  font: 400 11px var(--mono); color: var(--text-3); line-height: 1.65;
  white-space: pre-wrap; max-height: 180px; overflow-y: auto;
}
/* Download progress — the one animated element in the panel */
.u-bar {
  height: 4px; margin: 12px 0 8px; background: var(--border);
  overflow: hidden;
}
.u-fill { height: 100%; background: var(--brand); transition: width .3s; }
.u-foot {
  padding: 12px 16px; border-top: 1px solid var(--border);
  display: flex; gap: 8px; align-items: center;
}
.u-foot .grow { flex: 1; }
.u-ver { font: 400 10px var(--mono); color: var(--text-4); letter-spacing: .5px; }
.btn-sm.primary { border-color: var(--brand); color: var(--brand); }
.btn-sm.primary:hover { background: var(--brand); color: var(--on-brand); }
</style>
