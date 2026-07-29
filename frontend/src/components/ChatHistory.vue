<script setup>
import { store, loadHistory } from "../store.js";
</script>

<template>
  <div id="chat-history">
    <div class="panel-header"><span>History</span></div>
    <div v-for="(c, i) in store.chatHistory" :key="i" class="hist-row" @click="loadHistory(i)">
      <span class="ht">{{ c.title }}</span><span class="hw">{{ c.when }}</span>
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
.hist-row .ht { font: 500 12px var(--sans); color: var(--text-2); }
.hist-row:hover .ht { color: var(--text); }
.hist-row .hw { font: 400 10px var(--mono); color: var(--text-4); flex-shrink: 0; }
</style>
