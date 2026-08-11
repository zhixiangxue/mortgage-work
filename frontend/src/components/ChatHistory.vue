<script setup>
/* Real conversation list from the agent's `list` reply ({id,title,updated});
   clicking a row opens that conversation over the WS. */
import { onMounted, onUnmounted } from "vue";
import { store, showToast } from "../store.js";
import { openConv, deleteConv } from "../chatws.js";

/* "10:47 AM" for today, "Yesterday", then a short date — the same vocabulary
   the old mock rows used, now computed from the JSONL's mtime. */
function when(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const now = new Date();
  const startOfDay = t => new Date(t.getFullYear(), t.getMonth(), t.getDate());
  const days = Math.round((startOfDay(now) - startOfDay(d)) / 86400000);
  if (days <= 0) return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (days === 1) return "Yesterday";
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function close() { store.historyOpen = false; }

function onDelete(e, convId) {
  e.stopPropagation();
  if (confirm("Delete this conversation? This cannot be undone.")) {
    deleteConv(convId);
    showToast("Conversation deleted");
  }
}

// Press Escape to close the history overlay
function onKey(e) {
  if (!store.historyOpen) return;
  if (e.key === "Escape") close();
}

// Click anywhere outside the history panel closes it
function onClickOutside(e) {
  if (!store.historyOpen) return;
  const panel = document.getElementById("chat-history");
  if (panel && !panel.contains(e.target)) close();
}

onMounted(() => {
  document.addEventListener("keydown", onKey);
  document.addEventListener("click", onClickOutside);
});
onUnmounted(() => {
  document.removeEventListener("keydown", onKey);
  document.removeEventListener("click", onClickOutside);
});
</script>

<template>
  <div id="chat-history">
    <div class="panel-header">
      <span>History</span>
      <button class="x-btn" @click="close()">✕</button>
    </div>
    <div v-for="c in store.chat.convs" :key="c.id" class="hist-row" @click="openConv(c.id)">
      <span class="hw">{{ when(c.updated) }}</span>
      <span class="ht">{{ c.title }}</span>
      <span class="del-slot">
        <button class="del-btn" data-tip="Delete" @click="onDelete($event, c.id)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
        </button>
      </span>
    </div>
    <div v-if="!store.chat.convs.length" class="hist-empty">
      No conversations yet — every chat lands here once you send a message.
    </div>
  </div>
</template>

<style scoped>
/* History overlay covers the message area, flush against the header's
   bottom border. Must match #chat-header height: 11px padding × 2 + 15px
   icon height + 1px border = 38px. */
#chat-history {
  position: absolute; top: 38px; left: 0; right: 0; bottom: 0;
  background: var(--bg); z-index: 40; overflow-y: auto;
}
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  font: 700 10px var(--mono); letter-spacing: 2px; text-transform: uppercase;
  color: var(--text-3);
}
.x-btn {
  background: none; border: none; color: var(--text-4);
  font-size: 12px; cursor: pointer; padding: 0; line-height: 1;
}
.x-btn:hover { color: var(--red); }
.hist-row {
  padding: 10px 14px; cursor: pointer;
  border-bottom: 1px solid var(--bg-panel);
  display: flex; align-items: center; gap: 10px;
}
.hist-row:hover { background: var(--bg-hover); }
.hist-row .hw {
  font: 400 10px var(--mono); color: var(--text-4);
  flex-shrink: 0; width: 62px;
}
.hist-row .ht {
  font: 500 12px var(--sans); color: var(--text-2);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  flex: 1; min-width: 0;
}
.hist-row:hover .ht { color: var(--text); }
.del-slot {
  flex-shrink: 0; width: 16px;
  display: flex; align-items: center; justify-content: center;
}
.del-btn {
  background: none; border: none; color: var(--text-4);
  cursor: pointer; padding: 2px; line-height: 0;
  display: flex; opacity: 0; transition: opacity 0.15s, color 0.15s;
}
.del-btn svg { width: 13px; height: 13px; }
.hist-row:hover .del-btn { opacity: 1; }
.del-btn:hover { color: var(--red); }
.hist-empty { padding: 14px; font: 400 11px var(--mono); color: var(--text-4); }
</style>
