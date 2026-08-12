<script setup>
/* Settings — one unified pane, six sections. The gear in the activity bar
   opens this directly (no dropdown), and the left rail switches between
   LLM, Embedding, Memory, Voice, Connectors and Assistant Rules. */
import { ref, watch } from "vue";
import ModelSettings from "./ModelSettings.vue";
import EmbeddingSettings from "./EmbeddingSettings.vue";
import MemoryViewer from "./MemoryViewer.vue";
import VoiceSettings from "./VoiceSettings.vue";
import ConnectorSettings from "./ConnectorSettings.vue";
import AgentsSettings from "./AgentsSettings.vue";

const props = defineProps({
  initialSection: { type: String, default: "models" }
});
const active = ref(props.initialSection);

// When a deep link (e.g. Memory's "Open Embedding Settings") changes the
// initialSection while the pane is already open, switch to that tab.
watch(() => props.initialSection, (v) => { if (v) active.value = v; });
</script>

<template>
  <div id="doc-area" class="settings-root">
    <!-- Left rail: section switcher. Same restrained, IDE-like language as
         the activity bar — icon + label, brand highlight on the active row. -->
    <nav class="settings-nav">
      <div class="settings-nav-item" :class="{ active: active === 'models' }" @click="active = 'models'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        <span>LLM</span>
      </div>
      <div class="settings-nav-item" :class="{ active: active === 'embedding' }" @click="active = 'embedding'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/></svg>
        <span>Embedding</span>
      </div>
      <div class="settings-nav-item" :class="{ active: active === 'memory' }" @click="active = 'memory'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
        <span>Memory</span>
      </div>
      <div class="settings-nav-item" :class="{ active: active === 'voice' }" @click="active = 'voice'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
        <span>Voice</span>
      </div>
      <div class="settings-nav-item" :class="{ active: active === 'connectors' }" @click="active = 'connectors'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
        <span>Connectors</span>
      </div>
      <div class="settings-nav-item" :class="{ active: active === 'agents' }" @click="active = 'agents'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/></svg>
        <span>Assistant Rules</span>
      </div>
    </nav>

    <!-- Right content: the active section's component -->
    <div class="settings-content">
      <ModelSettings v-if="active === 'models'" />
      <EmbeddingSettings v-else-if="active === 'embedding'" />
      <MemoryViewer v-else-if="active === 'memory'" />
      <VoiceSettings v-else-if="active === 'voice'" />
      <ConnectorSettings v-else-if="active === 'connectors'" />
      <AgentsSettings v-else-if="active === 'agents'" />
    </div>
  </div>
</template>

<style scoped>
.settings-root {
  display: flex;
  height: 100%;
  min-height: 0;
}

/* Left rail — fixed width, matches the app's panel/border language */
.settings-nav {
  width: 200px; flex-shrink: 0;
  border-right: 1px solid var(--border);
  background: var(--bg-panel);
  padding: 14px 0;
}

.settings-nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 16px;
  cursor: pointer;
  font: 400 11px var(--mono);
  color: var(--text-4);
  border-left: 2px solid transparent;
  transition: color .12s, background .12s;
}
.settings-nav-item svg { width: 16px; height: 16px; flex-shrink: 0; }
.settings-nav-item:hover { color: var(--text-2); background: var(--bg-hover); }
.settings-nav-item.active {
  color: var(--brand);
  border-left-color: var(--brand);
  background: var(--bg);
}

/* Right content scrolls independently; child components render their own
   .md-doc padding and max-width. */
.settings-content {
  flex: 1; overflow-y: auto;
}
</style>
