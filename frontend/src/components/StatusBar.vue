<script setup>
import { store, syncNow, modelLabel } from "../store.js";
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
.demo-flag {
  color: var(--amber);
  /* Boot errors can be long — keep the bar intact */
  max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
</style>
