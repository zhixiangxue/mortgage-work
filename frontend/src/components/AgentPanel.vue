<script setup>
/* Developer-facing runtime panel. Services run on remote/cloud boxes: rows are
   read-only health + a door to each browser, no lifecycle controls from here. */
import { store, openDoc } from "../store.js";
import { SERVICES, viewerAvailable } from "../mocks/agent.js";

/* A viewer row stays visible when its data store isn't in .env — greying it
   out keeps the feature discoverable while saying "not enabled right now".
   Opening it still works: DocViewer plates "not configured" with the fix.
   Non-viewer rows (console) are never greyed. */
function isOff(s) {
  return s.name !== "console" && !viewerAvailable(s.name);
}
</script>

<template>
  <div class="wrap">
    <div class="panel-header">Runtime</div>

    <!-- Remote-hosted: health dots + open-the-browser rows only -->
    <div class="sect">SERVICES</div>
    <div v-for="s in SERVICES" :key="s.doc" class="rrow"
         :class="{ selected: store.active === s.doc, off: isOff(s) }"
         @click="openDoc(s.doc, 'runtime/' + s.name)">
      <span class="dot" :class="isOff(s) ? 'off' : s.status"></span>
      <span class="rname">{{ s.name }}</span>
      <span class="rmeta">{{ isOff(s) ? 'not configured' : s.status === 'restart' ? 'restarting…' : s.meta }}</span>
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow-y: auto; }
.sect {
  padding: 14px 14px 6px; font: 500 9.5px var(--mono);
  letter-spacing: 1.5px; color: var(--text-4);
  display: flex; align-items: center; justify-content: space-between;
}
.rrow {
  display: flex; align-items: center; gap: 8px;
  height: 26px; padding: 0 14px; cursor: pointer;
  font: 400 12px var(--mono); color: var(--text-2); white-space: nowrap;
}
.rrow:hover { background: var(--bg-hover); }
.rrow.selected { background: var(--bg-raise); color: var(--text); box-shadow: inset 2px 0 0 var(--brand); }
/* Unconfigured viewer: keep the row visible so the feature stays
   discoverable, but clearly mark it inactive instead of hiding it. */
.rrow.off .rname { color: var(--text-4); }
.rmeta { margin-left: auto; font-size: 10px; color: var(--text-4); }
/* Status dots: green = up, amber = working */
.dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; background: var(--text-4); }
.dot.off { opacity: .45; }
.dot.running, .dot.up { background: var(--brand); }
.dot.busy { background: var(--amber); animation: pulse 1.2s infinite; }
.dot.restart { background: var(--amber); animation: pulse .45s infinite; }
@keyframes pulse { 50% { opacity: .35; } }
</style>
