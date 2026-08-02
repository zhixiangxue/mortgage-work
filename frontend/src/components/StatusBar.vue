<script setup>
import { store, syncNow, modelLabel, retryIndexing } from "../store.js";
</script>

<template>
  <div id="statusbar">
    <span class="ctx">{{ store.sbCtx }}</span>
    <span class="warn">{{ store.sbWarn }}</span>
    <span class="right">
      <!-- Two honest states, no ambiguity: demo book (browser dev) vs a
           workspace that failed to load. The error outlives the toast. -->
      <span v-if="store.demo" class="demo-flag"
            data-tip="Plain-browser dev mode — everything shown is demo data">◆ DEMO DATA</span>
      <span v-else-if="!store.repo && store.bootError" class="demo-flag"
            :data-tip="'Workspace load failed: ' + store.bootError"
        >◆ WORKSPACE OFFLINE · {{ store.bootError }}</span>
      <span>{{ store.sbRight }}</span>
      <span id="sb-sync" :class="store.sync.cls" @click="syncNow()"
            data-tip="Backed up automatically — click to sync now">{{ store.sync.label }}</span>
      <!-- Indexing indicator: shown only when busy or failed. The reload
           icon on failed lets the user manually retry both RAG + KG sides. -->
      <span v-if="store.indexing.label" id="sb-index" :class="store.indexing.cls"
            @click="store.indexing.cls === 'failed' ? retryIndexing() : null"
            :data-tip="store.indexing.cls === 'failed'
              ? 'Click to retry indexing (RAG + KG)'
              : 'Indexing product documents to RAG & KG'">
        {{ store.indexing.label }}
        <svg v-if="store.indexing.cls === 'failed'" class="reload-icon" viewBox="0 0 16 16"
             width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.5"
             stroke-linecap="round" stroke-linejoin="round">
          <path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9"/>
          <path d="M14 2v3h-3"/>
        </svg>
      </span>
      <!-- Nothing in models.yaml means nothing to talk to — say so here too -->
      <span>{{ (modelLabel(store.currentModel) || "no model").toUpperCase() }}</span>
    </span>
  </div>
</template>

<style scoped>
#statusbar {
  height: 26px; background: var(--bg);
  border-top: 1px solid var(--border);
  display: flex; align-items: center;
  padding: 0 14px; gap: 18px;
  font: 500 10px var(--mono); letter-spacing: 1px; text-transform: uppercase;
  color: var(--text-3); flex-shrink: 0; user-select: none;
  /* One line, always — long contexts truncate, they never wrap the bar */
  white-space: nowrap; overflow: hidden;
}
#statusbar .ctx { color: var(--brand); min-width: 0; overflow: hidden; text-overflow: ellipsis; }
/* Warnings give way first (shrink harder) — the client context is the anchor */
#statusbar .warn { color: var(--amber); min-width: 0; overflow: hidden; text-overflow: ellipsis; flex-shrink: 4; }
#statusbar .right { margin-left: auto; display: flex; gap: 18px; flex-shrink: 0; }
/* Sync indicator — git under the hood, Dropbox language on the surface */
#sb-sync { cursor: pointer; }
#sb-sync.ok { color: var(--brand); }
#sb-sync.busy { color: var(--amber); animation: pulse 1.1s infinite; }
/* Offline: commits are safe locally, push owed — amber but calm (no pulse) */
#sb-sync.off { color: var(--amber); }
/* Indexing indicator — busy pulses, failed is solid amber with a reload icon */
#sb-index { cursor: default; display: inline-flex; align-items: center; gap: 4px; }
#sb-index.busy { color: var(--amber); animation: pulse 1.1s infinite; }
#sb-index.failed { color: var(--amber); cursor: pointer; }
#sb-index .reload-icon { vertical-align: middle; }
.demo-flag {
  color: var(--amber);
  /* Boot errors can be long — keep the bar intact */
  max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
</style>
