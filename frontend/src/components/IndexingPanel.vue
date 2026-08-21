<script setup>
/* Indexing Status panel — where every document stands in the indexing
   pipeline (one row per document; two columns speak the same status
   vocabulary as the database: pending / processing / done / failed /
   canceled). This is the PROCESS side of the knowledge base; the DATA
   side (what actually landed in the stores) lives in KbUnitsPane.vue
   and KbGraphPane.vue.

   A tab of its own: reachable from the sidebar KB tree header (its
   indexing indicator breathes while work is in flight) and the
   status-bar chip, so "what did it index?" is always one click away. */
import { ref, computed, onMounted } from "vue";
import { store, retryKnowledge, loadKnowledge } from "../store.js";

const filter = ref("all");

/* Document-level bucket, same priority as the backend summary
   (failed > processing > pending > canceled > done) — the tab counts can
   therefore never disagree with the chip counts. */
function bucket(row) {
  const sides = [row.rag_status, row.kg_status];
  for (const b of ["failed", "processing", "pending", "canceled"])
    if (sides.includes(b)) return b;
  return "done";
}

const rows = computed(() => store.knowledgeRows);
const filtered = computed(() =>
  filter.value === "all" ? rows.value : rows.value.filter(r => bucket(r) === filter.value));

const tabs = computed(() => {
  const k = store.knowledge;
  return [
    { id: "all",        label: "All",        n: k.total },
    { id: "pending",    label: "Pending",    n: k.pending },
    { id: "processing", label: "Processing", n: k.processing },
    { id: "failed",     label: "Failed",     n: k.failed },
    { id: "canceled",   label: "Canceled",   n: k.canceled },
  ];
});

/* file_path → name + folder line (folder name only, no products/ prefix) */
function fileName(path) {
  const i = path.lastIndexOf("/");
  return i < 0 ? path : path.slice(i + 1);
}
function folderName(path) {
  const i = path.lastIndexOf("/");
  if (i < 0) return "";
  const segs = path.slice(0, i).split("/");
  return segs[segs.length - 1] + "/";
}

/* Failure key → three sentences a loan officer can read. */
const ERROR_TEXT = {
  unavailable: "The knowledge service was temporarily unreachable. Click to retry this side.",
  timeout:     "Processing took too long and was abandoned. Click to retry this side.",
  vanished:    "The record was lost on the knowledge service. Click to retry this side.",
  unknown:     "Something went wrong while processing this side. Click to retry.",
};
function failTip(row, side) {
  return ERROR_TEXT[row[side + "_error"]] || ERROR_TEXT.unknown;
}

/* Relative time — the panel speaks "10 min ago", not ISO strings. */
function timeLabel(iso) {
  if (!iso) return "";
  const t = new Date(iso);
  if (isNaN(t)) return "";
  const diff = (Date.now() - t.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  const hm = t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const now = new Date();
  const sameDay = t.toDateString() === now.toDateString();
  if (sameDay) return `Today ${hm}`;
  const yest = new Date(now); yest.setDate(now.getDate() - 1);
  if (t.toDateString() === yest.toDateString()) return `Yesterday ${hm}`;
  if (diff < 7 * 86400) return `${Math.floor(diff / 86400)} days ago`;
  return t.toLocaleDateString([], { month: "short", day: "numeric" });
}

onMounted(() => {
  loadKnowledge();   // fresh pull in case no push landed yet
});
</script>

<template>
  <div id="indexing-panel">
    <!-- No page header — the tab title carries the name; the filter tabs
         with their counts are the content, straight away. -->
    <div class="tabs">
      <div v-for="t in tabs" :key="t.id" class="tab" :class="{ on: filter === t.id }"
           @click="filter = t.id">{{ t.label }}<span class="n">{{ t.n }}</span></div>
    </div>

    <table v-if="filtered.length" class="status-grid">
      <thead>
        <tr>
          <th style="width: 38%">Document</th>
          <th style="width: 18%">Document Index</th>
          <th style="width: 20%">Knowledge Graph</th>
          <th style="width: 16%">Time</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in filtered" :key="row.doc_id" :class="{ gone: bucket(row) === 'canceled' }">
          <td class="doc">
            <div class="name">{{ fileName(row.file_path) }}</div>
            <div class="meta">{{ folderName(row.file_path) }}</div>
          </td>
          <td v-for="side in ['rag', 'kg']" :key="side">
            <span v-if="row[side + '_status'] === 'done'" class="chip done">Done</span>
            <span v-else-if="row[side + '_status'] === 'processing'" class="chip working">
              <span class="spinner"></span>Processing</span>
            <span v-else-if="row[side + '_status'] === 'failed'" class="chip failed"
                  :title="failTip(row, side)" @click="retryKnowledge(row.doc_id, side)">
              <span class="t f">Failed</span><span class="t r">Retry</span></span>
            <span v-else-if="row[side + '_status'] === 'canceled'" class="chip canceled"
                  title="Superseded by a newer version of this document.">Canceled</span>
            <span v-else-if="row[side + '_status'] === 'na'" class="chip na"
                  title="This document type doesn't go through the knowledge graph.">N/A</span>
            <span v-else class="chip pending">Pending</span>
          </td>
          <td class="time">{{ timeLabel(row.updated_at) }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty">
      {{ rows.length ? "Nothing in this filter." : "Nothing indexed yet — add documents to the product library." }}
    </div>
  </div>
</template>

<style scoped>
#indexing-panel {
  flex: 1; min-height: 0; display: flex; flex-direction: column; overflow-y: auto;
  background: var(--bg-editor);
  padding: 18px 36px 24px; font: 13px var(--sans); color: var(--text);
}

/* ── filter tabs ── */
.tabs { display: flex; gap: 6px; margin-bottom: 14px; align-items: center; flex: none; }
.tab {
  padding: 4px 12px; font-size: 12px;
  color: var(--text-3); border: 1px solid var(--border);
  cursor: pointer; background: transparent;
}
.tab.on { background: var(--bg-raise); color: var(--text); border-color: var(--border-soft); }
.tab .n { color: var(--text-4); margin-left: 3px; }

/* ── status table ── */
table.status-grid { width: 100%; border-collapse: collapse; }
.status-grid th {
  text-align: left; font-size: 11px; font-weight: 500; color: var(--text-4);
  letter-spacing: .5px; padding: 8px 10px; border-bottom: 1px solid var(--border);
}
.status-grid td {
  padding: 10px; border-bottom: 1px solid var(--border);
  vertical-align: middle; white-space: nowrap;
}
.status-grid tr:hover td { background: var(--bg-hover); }

.doc .name { color: var(--text); }
.doc .meta { color: var(--text-4); font-size: 11px; margin-top: 2px; }
td.time { color: var(--text-4); font-size: 12px; }
tr.gone .name { color: var(--text-4); text-decoration: line-through; }

/* ── status chips: one shared vocabulary, both columns ─
   pending / processing / done / failed / canceled (+ N/A) */
.chip {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11.5px; padding: 3px 9px;
}
.chip.done    { background: var(--tint-green); color: var(--green); }
.chip.working { background: var(--tint-blue);  color: var(--blue); }
.chip.pending { color: var(--text-3); }
.chip.na      { color: var(--text-4); cursor: help; }
.chip.canceled{ color: var(--text-4); text-decoration: line-through; cursor: help; }
/* The check mark is an SVG mask, not the "✓" glyph — the glyph renders
   heavy and off-center next to the 11.5px label. Same mask technique as
   the retry icon below. */
.chip.done::before {
  content: ""; flex: none;
  width: 9px; height: 9px;
  background: currentColor;
  -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'/%3E%3C/svg%3E") center/contain no-repeat;
          mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'/%3E%3C/svg%3E") center/contain no-repeat;
}

/* A failed chip IS the retry button — the resting state is a quiet status
   pill (dot + word); on hover the whole chip transforms into the action. */
.chip.failed {
  background: var(--tint-red); color: var(--red);
  cursor: pointer;
  box-shadow: 0 0 0 1px transparent;
  transition: background .18s ease, color .18s ease,
              box-shadow .18s ease, transform .18s ease;
}
.chip.failed .t.r { display: none; }
.chip.failed::before {
  content: ""; flex: none;
  width: 6px; height: 6px; border-radius: 50%;
  background: currentColor;
  transition: all .18s ease;
}
.chip.failed:hover {
  background: var(--tint-green);
  background: color-mix(in srgb, var(--brand) 10%, transparent);
  color: var(--brand);
  box-shadow: 0 0 0 1px var(--brand), 0 3px 10px var(--tint-green);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--brand) 35%, transparent),
              0 3px 10px color-mix(in srgb, var(--brand) 12%, transparent);
  transform: translateY(-1px);
}
.chip.failed:hover .t.f { display: none; }
.chip.failed:hover .t.r { display: inline; }
.chip.failed:hover::before {
  width: 11px; height: 11px; border-radius: 0;
  -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M17.65 6.35A7.95 7.95 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z'/%3E%3C/svg%3E") center/contain no-repeat;
          mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M17.65 6.35A7.95 7.95 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z'/%3E%3C/svg%3E") center/contain no-repeat;
}
.chip.failed:active {
  transform: translateY(0);
  box-shadow: 0 0 0 1px var(--brand);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--brand) 35%, transparent);
}

.spinner {
  width: 10px; height: 10px; border-radius: 50%;
  border: 1.5px solid var(--blue);
  border-top-color: transparent;
  animation: sp .9s linear infinite;
}
@keyframes sp { to { transform: rotate(360deg); } }

.empty { color: var(--text-4); font-size: 12.5px; padding: 28px 10px; }
</style>
