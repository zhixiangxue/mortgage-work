<script setup>
/* Knowledge Base sidebar tree — the KB's own navigation, mounted where the
   file trees live. Two entries, each opening its own editor tab: Document
   Index (Qdrant points) and Knowledge Graph (FalkorDB graph), the two raw
   stores. The PROCESS face (Indexing Status) is not a tree row — it's a
   compact indicator on the header's right edge, breathing while work is
   in flight, one click opens the Indexing tab. */
import { computed } from "vue";
import { store, selectKbPane, openIndexing } from "../store.js";

const qInfo = computed(() => (store.kbBrowser.info || {}).qdrant || null);
const fInfo = computed(() => (store.kbBrowser.info || {}).falkordb || null);
const ok = side => side && !side.error;

/* A row reads as "current" only while its tab is the focused one — switch
   to another tab and the highlight steps aside. */
const on = id => store.active === id;

const ragCount = computed(() =>
  ok(qInfo.value) && qInfo.value.points != null
    ? `${Number(qInfo.value.points).toLocaleString()} units` : "");
const kgCount = computed(() =>
  ok(fInfo.value) && fInfo.value.products != null
    ? `${fInfo.value.products} products` : "");

/* Indexing indicator (header's right edge): breathing dot + counts while
   the pipeline works, a quiet dot once everything has settled. Failed
   outranks processing for the dot color. */
const idxLive = computed(() =>
  (store.knowledge.processing || 0) + (store.knowledge.failed || 0) > 0);
const idxCount = computed(() => {
  const p = store.knowledge.processing || 0, f = store.knowledge.failed || 0;
  const parts = [];
  if (p) parts.push(`${p} processing`);
  if (f) parts.push(`${f} failed`);
  return parts.join(" · ");
});
</script>

<template>
  <div class="wrap">
    <div class="panel-header">
      Knowledge Base
      <!-- The PROCESS face rides the header, not the tree — the tree lists
           stores, this shows the pipeline. Breathing dot + counts in
           flight, quiet once settled; one click opens the Indexing tab. -->
      <span class="icons">
        <span class="hic idx" :class="{ sel: on('indexing') }" data-tip="Indexing Status" @click="openIndexing()">
          <span class="kdot" :class="{ live: idxLive, bad: store.knowledge.failed > 0 }"></span>
          <span v-if="idxCount" class="kcount" :class="{ live: idxLive }">{{ idxCount }}</span>
        </span>
      </span>
    </div>
    <div class="tree">
      <div class="node krow" :class="{ selected: on('kbrag') }" @click="selectKbPane('rag')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
        <span class="fname">Document Index</span>
        <span class="kcount">{{ ragCount }}</span>
      </div>
      <div class="node krow" :class="{ selected: on('kbkg') }" @click="selectKbPane('kg')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
        <span class="fname">Knowledge Graph</span>
        <span class="kcount">{{ kgCount }}</span>
      </div>
      <!-- First load: info hasn't landed yet, keep the hint quiet -->
      <div v-if="!store.kbBrowser.info" class="kloading">loading store info…</div>
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; flex: 1; min-height: 0; }
/* Only two entries share this tree, so rows breathe — taller than file
   rows, roomier gap; the override beats the global .node's 24px */
.krow { height: 40px; padding-left: 12px; gap: 9px; font-size: 12.5px; }
.krow svg { width: 15px; height: 15px; flex: none; color: var(--text-4); }
.krow.selected svg { color: var(--brand); }
/* Trailing count sits where a git letter would — quiet mono, never pushed
   off-screen (the name ellipsises first); amber while work is in flight */
.kcount { margin-left: auto; color: var(--text-4); font: 400 10.5px var(--mono);
          white-space: nowrap; }
.kcount.live { color: var(--amber); }
.kloading { padding: 8px 12px; color: var(--text-4); font: 400 11px var(--mono); }
/* Header indexing indicator — dot + optional count ride one .hic; the
   global hover recolor is muted so in-flight amber keeps its urgency */
.hic.idx { gap: 5px; }
.hic.idx .kcount.live { color: var(--amber); }
.hic.idx:hover .kcount { color: var(--brand); }
.hic.idx:hover .kcount.live { color: var(--amber); }
.hic.idx.sel { color: var(--brand); }
/* Breathing presence dot (CSS circle, not a glyph) — quiet ring while
   settled, amber pulse in flight, red when something failed */
.kdot { width: 8px; height: 8px; border-radius: 50%; flex: none;
        border: 1px solid var(--border-soft); }
.kdot.live { background: var(--amber); border-color: transparent;
             animation: kdot-breathe 2.4s ease-in-out infinite; }
.kdot.live.bad { background: var(--red); }
@keyframes kdot-breathe { 0%, 100% { opacity: .35; transform: scale(.8); }
                          50% { opacity: 1; transform: scale(1); } }
</style>
