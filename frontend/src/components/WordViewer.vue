<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import * as mammoth from "mammoth";
import { showToast } from "../store.js";

const props = defineProps({
  bytes: { type: Uint8Array, required: true },
  scope: { type: String, default: "" },
  path: { type: String, default: "" },
  label: { type: String, default: "Document.docx" },
});

const wordHtml = ref("");
const loading = ref(true);
const error = ref("");
const workspaceEl = ref(null);

// ── Zoom (shared key with text editor / doc viewer) ──
const FONT_SIZE_KEY = "editor-font-size";
const DEFAULT_SIZE = 13;
const MIN = 10; const MAX = 20;

function readZoom() {
  try {
    const v = parseFloat(localStorage.getItem(FONT_SIZE_KEY));
    return Number.isFinite(v) ? Math.max(MIN, Math.min(MAX, v)) : DEFAULT_SIZE;
  } catch { return DEFAULT_SIZE; }
}

const zoom = ref(readZoom());

function applyZoom(el) {
  if (el) el.style.fontSize = zoom.value + "px";
}

function onWheel(e) {
  if (!e.ctrlKey && !e.metaKey) return;
  e.preventDefault();
  zoom.value = Math.max(MIN, Math.min(MAX, zoom.value + (e.deltaY < 0 ? 1 : -1)));
  applyZoom(workspaceEl.value);
  try { localStorage.setItem(FONT_SIZE_KEY, String(zoom.value)); } catch { /* quota */ }
}

// Bind Ctrl+Scroll to the workspace div whenever it materialises
watch(workspaceEl, (el, _, onCleanup) => {
  if (!el) return;
  applyZoom(el);
  el.addEventListener("wheel", onWheel, { passive: false });
  onCleanup(() => el.removeEventListener("wheel", onWheel));
});

// ── Parse .docx ──
function parseDocx() {
  loading.value = true;
  error.value = "";
  try {
    mammoth.convertToHtml({ arrayBuffer: props.bytes.buffer })
      .then(result => {
        wordHtml.value = result.value;
        if (result.messages.length) {
          const notes = result.messages.map(m => m.message).join("; ");
          showToast("Word preview may have formatting differences: " + notes, "warn");
        }
        loading.value = false;
      })
      .catch(err => {
        error.value = err.message || "Failed to parse this Word document";
        loading.value = false;
      });
  } catch (err) {
    error.value = err.message || "Failed to parse this Word document";
    loading.value = false;
  }
}

parseDocx();
watch(() => props.bytes, parseDocx);

// ── Open in Word ──
function openExternal() {
  if (!window.pywebview || !props.scope || !props.path) return;
  window.pywebview.api.open_external(props.scope, props.path);
}
</script>

<template>
  <div class="ww-root">
    <!-- Toolbar -->
    <div class="ww-toolbar">
      <span class="ww-title">
        <span class="ww-dot"></span>
        Preview only — formatting may differ from the original document.
      </span>
      <span class="ww-actions">
        <button class="ww-btn ww-btn-primary" @click="openExternal">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M10 2h3a1 1 0 011 1v10a1 1 0 01-1 1h-3M6.5 4.5L10 8l-3.5 3.5M10 8H2"/>
          </svg>
          Open in Word
        </button>
      </span>
    </div>

    <!-- Workspace -->
    <div class="ww-workspace" ref="workspaceEl">
      <!-- Loading -->
      <div v-if="loading" class="ww-status">
        <div class="ww-spin"></div>
        <div class="ww-status-text">Parsing document…</div>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="ww-status">
        <div class="ww-err-icon">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>
        </div>
        <div class="ww-status-text">{{ error }}</div>
      </div>

      <!-- Rendered page -->
      <div v-else class="ww-page" v-html="wordHtml"></div>
    </div>
  </div>
</template>

<style scoped>
.ww-root {
  display: flex; flex-direction: column;
  height: 100%; background: var(--bg);
}

/* ── Toolbar ── */
.ww-toolbar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px; background: var(--bg-hover);
  border-bottom: 1px solid var(--border); user-select: none; flex-shrink: 0;
}
.ww-title {
  font: 400 11px var(--sans); color: var(--text-4);
  display: flex; align-items: center; gap: 7px;
  overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
}
.ww-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--amber); flex-shrink: 0; }
.ww-actions { margin-left: auto; display: flex; gap: 8px; }
.ww-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 14px; border-radius: 5px; cursor: pointer;
  font: 500 11.5px var(--sans); border: 1px solid var(--border);
  background: var(--bg); color: var(--text); transition: .15s;
}
.ww-btn:hover { border-color: var(--brand); color: var(--brand); }
.ww-btn-primary {
  background: var(--brand); color: #0d1117; border-color: var(--brand); font-weight: 600;
}
.ww-btn-primary:hover { opacity: .88; color: #0d1117; }
.ww-btn svg { flex-shrink: 0; }

/* ── Workspace ── */
.ww-workspace {
  flex: 1; overflow-y: auto; overflow-x: hidden;
  min-height: 0;
  background: color-mix(in srgb, var(--bg) 92%, #000);
  display: flex; flex-direction: column; align-items: center;
  padding: 28px 0 48px;
  font-size: 13px;
}

/* ── Status (loading / error) ── */
.ww-status {
  display: flex; flex-direction: column; align-items: center; gap: 14px;
  margin-top: 80px; color: var(--text-4);
}
.ww-spin {
  width: 22px; height: 22px; border-radius: 50%;
  border: 2px solid var(--border); border-top-color: var(--brand);
  animation: ww-rot .7s linear infinite;
}
@keyframes ww-rot { to { transform: rotate(360deg); } }
.ww-err-icon { color: var(--amber); }
.ww-status-text { font: 400 12px var(--sans); }

/* ── Page (white paper on dark bg) ── */
.ww-page {
  width: min(960px, 100%);
  background: #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,.4), 0 2px 12px rgba(0,0,0,.25);
  padding: clamp(32px, 5vw, 72px) clamp(24px, 7vw, 96px);
  font-family: var(--sans);
  color: #1f2328;
  line-height: 1.65;
  flex-shrink: 0;
}

/* All page content uses em/rem so Ctrl+Scroll zoom works */
.ww-page :deep(h1) { font: 700 1.75em var(--sans); color: #1f2328; margin: .3em 0; }
.ww-page :deep(h2) { font: 600 1.25em var(--sans); color: #1f2328; margin: 2em 0 .6em; padding-bottom: .3em; border-bottom: 1px solid #d0d7de; }
.ww-page :deep(h3) { font: 600 1.05em var(--sans); color: #1f2328; margin: 1.5em 0 .4em; }
.ww-page :deep(p)  { font: 400 .95em/1.75 var(--sans); color: #454c54; margin: .5em 0; }
.ww-page :deep(strong) { color: #1f2328; }
.ww-page :deep(ul), .ww-page :deep(ol) { margin: .5em 0; padding-left: 1.8em; font: 400 .95em/1.8 var(--sans); color: #454c54; }
.ww-page :deep(li) { margin: .15em 0; }
.ww-page :deep(li::marker) { color: #8b949e; }

.ww-page :deep(table) {
  border-collapse: collapse; width: 100%; margin: 1em 0;
  font: 400 .9em var(--sans); border: 1px solid #d0d7de;
}
.ww-page :deep(th) {
  background: #f6f8fa; text-align: left; padding: .6em .7em;
  font-weight: 600; font-size: .8em; letter-spacing: .5px; text-transform: uppercase;
  color: #656d76; border-bottom: 2px solid #d0d7de;
}
.ww-page :deep(td) {
  padding: .55em .7em; color: #454c54;
  border-bottom: 1px solid #e2e5e9;
}
.ww-page :deep(tr:nth-child(even) td) { background: #f6f8fa; }

.ww-page :deep(img) {
  max-width: 100%; height: auto;
  border: 1px solid #e2e5e9; border-radius: 2px;
  margin: .8em 0;
}
</style>
