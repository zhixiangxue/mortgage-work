<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import * as XLSX from "xlsx";
import { showToast } from "../store.js";

const props = defineProps({
  bytes: { type: Uint8Array, required: true },
  scope: { type: String, default: "" },
  path: { type: String, default: "" },
  label: { type: String, default: "Workbook.xlsx" },
});

// ── Parse workbook ──
const sheets = ref([]);      // [{ name, rows, maxCols }]
const activeIdx = ref(0);
const loading = ref(true);
const error = ref("");
const workspaceEl = ref(null);
const gridEl = ref(null);

const activeSheet = computed(() => sheets.value[activeIdx.value] || null);
const colLetters = computed(() => {
  const n = activeSheet.value?.maxCols || 0;
  const cols = [];
  for (let i = 0; i < n; i++) {
    let col = "";
    let c = i;
    while (c >= 0) {
      col = String.fromCharCode(65 + (c % 26)) + col;
      c = Math.floor(c / 26) - 1;
    }
    cols.push(col);
  }
  return cols;
});

// ── Zoom ──
const FONT_SIZE_KEY = "editor-font-size";
const DEFAULT_SIZE = 12;
const MIN = 9; const MAX = 18;

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

watch(workspaceEl, (el, _, onCleanup) => {
  if (!el) return;
  applyZoom(el);
  el.addEventListener("wheel", onWheel, { passive: false });
  onCleanup(() => el.removeEventListener("wheel", onWheel));
});

// ── Parse .xlsx ──
function parseWorkbook() {
  loading.value = true;
  error.value = "";
  try {
    const wb = XLSX.read(props.bytes.buffer, { type: "array" });
    const parsed = wb.SheetNames.map(name => {
      const ws = wb.Sheets[name];
      const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: "" });
      const maxCols = rows.reduce((m, r) => Math.max(m, Array.isArray(r) ? r.length : 0), 0);
      return { name, rows, maxCols };
    });
    sheets.value = parsed;
    activeIdx.value = 0;
    loading.value = false;
  } catch (err) {
    error.value = err.message || "无法解析该 Excel 工作簿";
    loading.value = false;
  }
}

function switchSheet(idx) {
  activeIdx.value = idx;
  // Reset scroll position
  if (gridEl.value) {
    gridEl.value.scrollTop = 0;
    gridEl.value.scrollLeft = 0;
  }
}

parseWorkbook();
watch(() => props.bytes, parseWorkbook);

// ── Cell class helpers ──
function cellClass(val) {
  if (typeof val === "number") return "num";
  return "";
}
function fmtCell(val) {
  if (val == null || val === "") return "";
  if (typeof val === "number") {
    // Format as currency-like if > 100
    if (Math.abs(val) >= 100) {
      return val.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 0, maximumFractionDigits: 0 });
    }
    return val.toLocaleString("en-US");
  }
  return String(val);
}

// Detect if a sheet has many columns → apply .wide class for larger min cell width
const isWide = computed(() => (activeSheet.value?.maxCols || 0) >= 14);

// ── Open in Excel ──
function openExternal() {
  if (!window.pywebview || !props.scope || !props.path) return;
  window.pywebview.api.open_external(props.scope, props.path);
}
</script>

<template>
  <div class="ew-root">
    <!-- Toolbar -->
    <div class="ew-toolbar">
      <span class="ew-title">
        <span class="ew-dot"></span>
        Preview only — formulas, charts, and conditional formatting may differ from the original workbook.
      </span>
      <span class="ew-actions">
        <button class="ew-btn ew-btn-primary" @click="openExternal">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M10 2h3a1 1 0 011 1v10a1 1 0 01-1 1h-3M6.5 4.5L10 8l-3.5 3.5M10 8H2"/>
          </svg>
          Open in Excel
        </button>
      </span>
    </div>

    <!-- Workspace -->
    <div class="ew-workspace" ref="workspaceEl">
      <!-- Loading -->
      <div v-if="loading" class="ew-status">
        <div class="ew-spin"></div>
        <div class="ew-status-text">Parsing workbook…</div>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="ew-status">
        <div class="ew-err-icon">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>
        </div>
        <div class="ew-status-text">{{ error }}</div>
      </div>

      <!-- Grid -->
      <template v-else-if="sheets.length">
        <div class="ew-grid-area" ref="gridEl">
          <div class="ew-sheet-container">
            <table :class="['ew-grid', isWide ? 'ew-wide' : '']" :data-sheet="activeSheet.name">
              <thead>
                <tr>
                  <th class="ew-rh"></th>
                  <th v-for="c in colLetters" :key="c">{{ c }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in activeSheet.rows" :key="ri">
                  <td class="ew-rh">{{ ri + 1 }}</td>
                  <td v-for="ci in activeSheet.maxCols"
                      :key="ci"
                      :class="[cellClass(row[ci - 1]), row[ci - 1] != null && row[ci - 1] !== '' && typeof row[ci - 1] === 'number' ? 'ew-num' : '']"
                      v-text="fmtCell(row[ci - 1])"></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Sheet bar (fixed at bottom) -->
        <div class="ew-sheet-bar">
          <div class="ew-sheet-tabs">
            <span v-for="(s, i) in sheets" :key="s.name"
                  :class="['ew-sheet-tab', { active: i === activeIdx }]"
                  @click="switchSheet(i)">{{ s.name }}</span>
          </div>
        </div>
      </template>

      <!-- Empty workbook -->
      <div v-else class="ew-status">
        <div class="ew-status-text">Workbook contains no sheets.</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ew-root {
  display: flex; flex-direction: column;
  height: 100%; background: var(--bg);
}

/* ── Toolbar ── */
.ew-toolbar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px; background: var(--bg-hover);
  border-bottom: 1px solid var(--border); user-select: none; flex-shrink: 0;
}
.ew-title {
  font: 400 11px var(--sans); color: var(--text-4);
  display: flex; align-items: center; gap: 7px;
  overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
}
.ew-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--amber); flex-shrink: 0; }
.ew-actions { margin-left: auto; display: flex; gap: 8px; }
.ew-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 14px; border-radius: 5px; cursor: pointer;
  font: 500 11.5px var(--sans); border: 1px solid var(--border);
  background: var(--bg); color: var(--text); transition: .15s;
}
.ew-btn:hover { border-color: var(--brand); color: var(--brand); }
.ew-btn-primary {
  background: var(--brand); color: #0d1117; border-color: var(--brand); font-weight: 600;
}
.ew-btn-primary:hover { opacity: .88; color: #0d1117; }
.ew-btn svg { flex-shrink: 0; }

/* ── Workspace ── */
.ew-workspace {
  flex: 1; display: flex; flex-direction: column;
  min-height: 0;
  background: color-mix(in srgb, var(--bg) 92%, #000);
  font-size: 12px;
}

/* ── Status ── */
.ew-status {
  display: flex; flex-direction: column; align-items: center; gap: 14px;
  margin-top: 80px; color: var(--text-4);
}
.ew-spin {
  width: 22px; height: 22px; border-radius: 50%;
  border: 2px solid var(--border); border-top-color: var(--brand);
  animation: ew-rot .7s linear infinite;
}
@keyframes ew-rot { to { transform: rotate(360deg); } }
.ew-err-icon { color: var(--amber); }
.ew-status-text { font: 400 12px var(--sans); }

/* ── Grid area (scrollable) ── */
.ew-grid-area {
  flex: 1; overflow: auto;
  min-height: 0;
  background: color-mix(in srgb, var(--bg) 92%, #000);
}
.ew-sheet-container {
  background: #fff;
  display: inline-block;
  min-width: 100%;
}

/* ── Excel-like grid table ── */
.ew-grid {
  border-collapse: collapse; font: 400 .92em/1.4 var(--sans); color: #1f2328;
  width: 100%; min-width: max-content;
}
.ew-grid th, .ew-grid td {
  border: 1px solid #d4d8dd;
  padding: 3px 7px;
  min-width: 72px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 320px;
}
/* Wide table: bump min cell width so many-column sheets overflow → scrollbar */
.ew-grid.ew-wide th, .ew-grid.ew-wide td { min-width: 96px; }

/* Row header (1,2,3…) — frozen left */
.ew-grid .ew-rh {
  background: #f3f4f6; color: #656d76;
  text-align: center; font: 400 .83em var(--mono);
  min-width: 42px; width: 42px;
  border-right: 2px solid #c4c9cf;
  user-select: none;
  position: sticky; left: 0; z-index: 1;
}
/* Col header (A,B,C…) — frozen top */
.ew-grid thead th {
  background: #f3f4f6; color: #656d76;
  text-align: center; font: 400 .83em var(--mono);
  border-bottom: 2px solid #c4c9cf;
  user-select: none;
  position: sticky; top: 0; z-index: 2;
}
/* Corner freeze: row + col header intersection */
.ew-grid thead th:first-child {
  border-right: 2px solid #c4c9cf;
  position: sticky; left: 0; top: 0; z-index: 3;
}
.ew-grid td { background: #fff; }
.ew-grid td.ew-num { text-align: right; font-variant-numeric: tabular-nums; }

/* ── Sheet bar (fixed at bottom of workspace) ── */
.ew-sheet-bar {
  flex-shrink: 0;
  background: #e8eaed;
  border-top: 1px solid #d0d7de;
  user-select: none;
}
.ew-sheet-tabs {
  display: flex; gap: 2px;
  padding: 4px 8px 0;
}
.ew-sheet-tab {
  padding: 6px 16px;
  font: 400 .92em var(--sans);
  color: #656d76;
  background: #e8eaed;
  border: 1px solid transparent;
  border-bottom: none;
  border-radius: 4px 4px 0 0;
  cursor: pointer;
  transition: .12s;
}
.ew-sheet-tab:hover { background: #dcdfe4; color: #454c54; }
.ew-sheet-tab.active {
  background: #fff;
  color: #1f2328;
  font-weight: 600;
  border-color: #d0d7de;
  position: relative;
  z-index: 1;
  margin-bottom: -1px;
  border-bottom: 1px solid #fff;
}
</style>
