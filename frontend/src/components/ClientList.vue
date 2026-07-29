<script setup>
import { store, openClient, openNewClient, openClientListCtx } from "../store.js";
</script>

<template>
  <div class="wrap">
    <div class="panel-header">
      Clients
      <span class="icons">
        <span data-tip="New client" @click="openNewClient()">＋</span>
        <span data-tip="Refresh">⟳</span>
      </span>
    </div>
    <div id="side-clients" @contextmenu.prevent="openClientListCtx($event)">
      <div v-for="c in store.clients.concat(store.closed)" :key="c.id"
           class="client-row" :class="{ selected: store.client && store.client.id === c.id }"
           @click="openClient(c.id)"
           @contextmenu.prevent.stop="openClientListCtx($event, c.id)">
        <div class="cname">{{ c.name }}<span class="when">{{ c.touched }}</span></div>
        <div class="cpurpose">{{ c.purpose }} · <span class="amt">{{ c.amount }}</span></div>
        <div class="cmeta">
          <span class="stage" :class="c.stage">{{ c.stageLbl }}</span>
          <span v-if="c.missing" class="miss">{{ c.missing }} missing</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; flex: 1; min-height: 0; }
#side-clients { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }
.client-row {
  padding: 12px 14px 13px; cursor: pointer;
  border-bottom: 1px solid var(--bg-panel);
}
.client-row:hover { background: var(--bg-hover); }
.client-row.selected { background: var(--bg-raise); box-shadow: inset 2px 0 0 var(--brand); }
/* Line 1: who + last touch (top-right, mail-client style) */
.client-row .cname {
  font: 600 13px var(--sans); color: var(--text-2);
  display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
}
.client-row:hover .cname { color: var(--text); }
.client-row .when { font: 400 9.5px var(--mono); color: var(--text-4); flex-shrink: 0; }
/* Line 2: purpose + amount — same triage line as the welcome cards */
.client-row .cpurpose { margin-top: 5px; font: 400 10px var(--mono); color: var(--text-4); }
.client-row .cpurpose .amt { color: var(--text-3); }
/* Line 3: where it's stuck */
.client-row .cmeta { margin-top: 8px; font: 400 10px var(--mono); color: var(--text-4); display: flex; gap: 8px; align-items: center; }
</style>
