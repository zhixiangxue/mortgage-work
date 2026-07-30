<script setup>
/* Real conversation list from the agent's `list` reply ({id,title,updated});
   clicking a row opens that conversation over the WS. */
import { store } from "../store.js";
import { openConv } from "../chatws.js";

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
</script>

<template>
  <div id="chat-history">
    <div class="panel-header"><span>History</span></div>
    <div v-for="c in store.chat.convs" :key="c.id" class="hist-row" @click="openConv(c.id)">
      <span class="ht">{{ c.title }}</span><span class="hw">{{ when(c.updated) }}</span>
    </div>
    <div v-if="!store.chat.convs.length" class="hist-empty">
      No conversations yet — every chat lands here once you send a message.
    </div>
  </div>
</template>

<style scoped>
/* History overlay covers the message area, dropdown-style */
#chat-history {
  position: absolute; top: 39px; left: 0; right: 0; bottom: 0;
  background: var(--bg); z-index: 40; overflow-y: auto;
}
.hist-row {
  padding: 10px 14px; cursor: pointer;
  border-bottom: 1px solid var(--bg-panel);
  display: flex; align-items: baseline; justify-content: space-between; gap: 10px;
}
.hist-row:hover { background: var(--bg-hover); }
.hist-row .ht {
  font: 500 12px var(--sans); color: var(--text-2);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.hist-row:hover .ht { color: var(--text); }
.hist-row .hw { font: 400 10px var(--mono); color: var(--text-4); flex-shrink: 0; }
.hist-empty { padding: 14px; font: 400 11px var(--mono); color: var(--text-4); }
</style>
