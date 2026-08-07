<script setup>
/* Sidebar panel: memory bank list. One bank today (Work Memory); more when
   User Preferences gets its own seeka store. Clicking a bank opens the
   matching editor tab where the LO browses, edits and deletes memories. */
import { computed } from "vue";
import { store, showToast,
         loadMemoryConfig, openMemoryBank,
         toggleMemory, forgetMemories } from "../store.js";

/* Renders green when memory is on and actively extracting, grey when off,
   amber when the embedder was configured but the provider is no longer
   keyed (e.g. the LO rotated keys). */
const bankActive = computed(() => store.active === "memory");

/* When embedding isn't configured yet, the toggle becomes a shortcut: flip
   enabled optimistically so the editor pane shows the setup card instead of
   the "off" empty state, then open the tab. No backend call — the LO hasn't
   picked a provider yet, so there's nothing to save. */
function onToggle() {
  if (!store.memory.embedding) {
    store.memory.enabled = !store.memory.enabled;
    openMemoryBank();
    return;
  }
  toggleMemory(!store.memory.enabled);
}

const SVG_TRASH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>`;
</script>

<template>
  <div class="wrap">
    <div class="panel-header">Memory</div>
    <div class="bank-list">
      <!-- Row: Work Memory (living, the one mem-agent fills) -->
      <div class="bank-row" :class="{ active: bankActive }" @click="openMemoryBank()">
        <div class="bank-row-top">
          <span class="bank-name">Work Memory</span>
          <div class="toggle" :class="{ on: store.memory.enabled }"
               title="Enable / disable auto-extraction"
               @click.stop="onToggle">
            <span class="slider"></span>
          </div>
        </div>
        <div class="bank-meta">
          <span class="bank-count">{{ store.memory.memos.length }} memories</span>
        </div>
        <button class="del-btn" title="Delete all memories in this bank"
                @click.stop="forgetMemories()" v-html="SVG_TRASH">
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow-y: auto; }

.bank-row {
  padding: 12px 14px; cursor: pointer; position: relative;
  border-bottom: 1px solid var(--bg-panel);
}
.bank-row:hover { background: var(--bg-hover); }
.bank-row.active { background: var(--bg-raise); box-shadow: inset 2px 0 0 var(--brand); }
.bank-row-top {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.bank-name { font: 600 13px var(--sans); color: var(--text-2); }
.bank-row.active .bank-name { color: var(--text); }

/* Delete button: appears bottom-right on hover */
.bank-row .del-btn {
  position: absolute; right: 10px; bottom: 8px;
  width: 22px; height: 22px; display: flex; align-items: center; justify-content: center;
  border: none; background: var(--bg-panel); border-radius: 4px; cursor: pointer;
  color: var(--text-4); opacity: 0; transition: opacity .15s;
}
.bank-row:hover .del-btn { opacity: 1; }
.bank-row .del-btn:hover { background: rgba(235,54,28,.15); color: var(--red); }
.bank-row .del-btn :deep(svg) { width: 13px; height: 13px; }

.bank-meta { margin-top: 6px; }
.bank-count { font: 400 10px var(--mono); color: var(--text-4); }

/* Toggle (inline, square knob matching the brand-green slider) */
.toggle { position: relative; width: 30px; height: 17px; flex-shrink: 0; cursor: pointer; }
.toggle .slider {
  position: absolute; cursor: pointer; inset: 0; background: var(--border-soft);
  border-radius: 3px; transition: .25s;
}
.toggle .slider::before {
  content: ""; position: absolute; height: 11px; width: 11px; left: 3px; top: 3px;
  background: var(--text); border-radius: 2px; transition: .25s;
}
.toggle.on .slider { background: var(--brand); }
.toggle.on .slider::before { transform: translateX(13px); background: var(--on-brand); }
</style>
