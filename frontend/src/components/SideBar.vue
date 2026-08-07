<script setup>
/* Five-state container: client list / focused client tree / product library / tools / agent runtime */
import { store } from "../store.js";
import ClientList from "./ClientList.vue";
import ClientTree from "./ClientTree.vue";
import ProductTree from "./ProductTree.vue";
import ToolsPanel from "./ToolsPanel.vue";
import AgentPanel from "./AgentPanel.vue";
</script>

<template>
  <div id="sidebar">
    <AgentPanel v-if="store.view === 'agent'" />
    <ToolsPanel v-else-if="store.view === 'tools'" />
    <ProductTree v-else-if="store.view === 'products'" />
    <ClientTree v-else-if="store.client" />
    <ClientList v-else />
  </div>
</template>

<style scoped>
#sidebar {
  width: 310px; min-width: 220px; max-width: 480px;
  background: var(--bg); border-right: 1px solid var(--border);
  display: flex; flex-direction: column; flex-shrink: 0; user-select: none;
}
</style>
