<script setup>
import { computed } from "vue";
import { store, switchView, closeClient, openSettings, openKnowledge } from "../store.js";

// The gear highlights when the Settings tab is the active doc; same idea
// for the database icon and the Knowledge Base tab.
const gearActive = computed(() => store.active === "settings");
const kbActive = computed(() => store.active === "knowledge");

// When a tab-panel (Settings / Knowledge Base) is the focused tab, the
// sidebar view buttons step aside — only one activity-bar icon should be
// lit at a time. Clicking any view button re-takes the focus (the click
// handler drops the panel focus).
const navDim = computed(() => store.active === "settings" || store.active === "knowledge");

function navClick(fn) {
  // Leaving a panel pane: if it's the focused tab, pull focus back to the
  // sidebar so the view icon lights up instead of the panel icon.
  if (store.active === "settings" || store.active === "knowledge") store.active = null;
  fn();
}

// Clicking Clients while already inside a client backs out to the list — the
// button is the way home, not a no-op once a client is open.
function clickClients() {
  if (store.view === "clients" && store.client) closeClient();
  else switchView("clients");
}

function clickProducts() { switchView("products"); }
function clickTools() { switchView("tools"); }
</script>

<template>
  <div id="activitybar">
    <div class="act" :class="{ active: store.view === 'clients' && !navDim }" data-tip="Clients" @click="navClick(clickClients)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="7.5" r="4"/><path d="M4.5 21c.6-4 3.6-6.5 7.5-6.5s6.9 2.5 7.5 6.5"/></svg>
    </div>
    <div class="act" :class="{ active: store.view === 'products' && !navDim }" data-tip="Product Library" @click="navClick(clickProducts)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
    </div>
    <!-- Knowledge Base: opens the panel tab directly, same shape as the
         Settings gear — the sidebar keeps its view list, the panel is a
         destination of its own. -->
    <div class="act" :class="{ active: kbActive }" data-tip="Knowledge Base" @click="openKnowledge()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/><path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/></svg>
    </div>
    <div class="act" :class="{ active: store.view === 'tools' && !navDim }" data-tip="Tools" @click="navClick(clickTools)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
    </div>
    <div class="spacer"></div>
    <!-- Settings gear: one click opens the unified Settings tab directly —
         no dropdown. The section switcher (Models / Workspace Instructions)
         lives inside the pane itself. -->
    <div class="act" :class="{ active: gearActive }" data-tip="Settings" @click="openSettings()">
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
</style>
