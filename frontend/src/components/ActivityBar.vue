<script setup>
import { store, switchView, openDoc } from "../store.js";
</script>

<template>
  <div id="activitybar">
    <div class="act" :class="{ active: store.view === 'clients' }" data-tip="Clients" @click="switchView('clients')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="7.5" r="4"/><path d="M4.5 21c.6-4 3.6-6.5 7.5-6.5s6.9 2.5 7.5 6.5"/></svg>
    </div>
    <div class="act" :class="{ active: store.view === 'products' }" data-tip="Product Library" @click="switchView('products')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
    </div>
    <div class="act" :class="{ active: store.view === 'agent' }" data-tip="Agent Runtime" @click="switchView('agent')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/></svg>
    </div>
    <div class="spacer"></div>
    <div class="gear" data-tip="Settings — models" @click="openDoc('models')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
    </div>
  </div>
</template>

<style scoped>
#activitybar {
  width: 46px; flex-shrink: 0;
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; align-items: center;
  padding-top: 6px; user-select: none;
}
/* Icon-only entries like mainstream IDEs; native title tooltip on hover */
.act {
  width: 46px; height: 46px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; color: var(--text-4);
  position: relative;
}
.act svg { width: 21px; height: 21px; }
.act:hover { color: var(--text-2); }
.act.active { color: var(--brand); }
.act.active::before {
  content: ""; position: absolute; left: 0; top: 8px; bottom: 8px;
  width: 2px; background: var(--brand);
}
.spacer { flex: 1; }
.gear { padding: 14px 0; color: var(--text-4); cursor: pointer; }
.gear svg { width: 20px; height: 20px; }
.gear:hover { color: var(--text-2); }
</style>
