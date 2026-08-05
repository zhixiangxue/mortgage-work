<script setup>
import { ref, onMounted, onUnmounted } from "vue";
import { store, switchView, closeClient, openModelSettings, openAgentsSettings } from "../store.js";

// Clicking Clients while already inside a client backs out to the list — the
// button is the way home, not a no-op once a client is open.
function clickClients() {
  if (store.view === "clients" && store.client) closeClient();
  else switchView("clients");
}

// Settings dropdown — gear now opens a small menu instead of going straight
// to models. Two settings panes (models + workspace instructions) need entries.
const settingsOpen = ref(false);

function toggleSettings(e) {
  e.stopPropagation();
  settingsOpen.value = !settingsOpen.value;
}
function closeSettings() { settingsOpen.value = false; }

function pickModel() { settingsOpen.value = false; openModelSettings(); }
function pickAgents() { settingsOpen.value = false; openAgentsSettings(); }

onMounted(() => document.addEventListener("click", closeSettings));
onUnmounted(() => document.removeEventListener("click", closeSettings));
</script>

<template>
  <div id="activitybar">
    <div class="act" :class="{ active: store.view === 'clients' }" data-tip="Clients" @click="clickClients()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="7.5" r="4"/><path d="M4.5 21c.6-4 3.6-6.5 7.5-6.5s6.9 2.5 7.5 6.5"/></svg>
    </div>
    <div class="act" :class="{ active: store.view === 'products' }" data-tip="Product Library" @click="switchView('products')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
    </div>
    <div class="act" :class="{ active: store.view === 'tools' }" data-tip="Tools" @click="switchView('tools')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
    </div>
    <div class="act" :class="{ active: store.view === 'agent' }" data-tip="Agent Runtime" @click="switchView('agent')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/></svg>
    </div>
    <div class="spacer"></div>
    <div class="gear-wrap">
      <div class="gear" :class="{ active: settingsOpen }" data-tip="Settings" @click="toggleSettings($event)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
      </div>
      <!-- Settings dropdown — two panes, one gear. Click-outsides close it
           (listener on document), item clicks close it by nulling the ref. -->
      <div class="gear-dd" v-if="settingsOpen" @click.stop>
        <div class="gear-dd-item" @click="pickModel()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
          <span>Models &amp; Providers</span>
        </div>
        <div class="gear-dd-item" @click="pickAgents()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/></svg>
          <span>Workspace Instructions</span>
        </div>
      </div>
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
.gear-wrap { position: relative; }
.gear { padding: 14px 0; color: var(--text-4); cursor: pointer; }
.gear svg { width: 20px; height: 20px; }
.gear:hover, .gear.active { color: var(--text-2); }

/* Dropdown — same visual language as the provider picker in ModelSettings */
.gear-dd {
  position: absolute; bottom: 0; left: 100%; margin-left: 4px;
  background: var(--bg-raise); border: 1px solid var(--border);
  box-shadow: 0 4px 16px rgba(0,0,0,.25);
  min-width: 200px; z-index: 100;
}
.gear-dd-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; cursor: pointer;
  font: 400 11px var(--mono); color: var(--text-2);
  border-bottom: 1px solid var(--border-soft);
}
.gear-dd-item:last-child { border-bottom: none; }
.gear-dd-item:hover { background: var(--bg); color: var(--text); }
.gear-dd-item svg { width: 16px; height: 16px; flex-shrink: 0; color: var(--text-4); }
.gear-dd-item:hover svg { color: var(--text-2); }
</style>
