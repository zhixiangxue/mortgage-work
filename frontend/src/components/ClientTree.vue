<script setup>
import { store, closeClient, openCtxMenu, dragFilesOver, dragFilesLeave, dropFilesAt } from "../store.js";
import TreeNodes from "./TreeNodes.vue";

/* Right-click on empty tree space targets the folder root */
function onRootCtx(e) {
  e.preventDefault();
  openCtxMenu(e, null);
}
</script>

<template>
  <div class="wrap">
    <div class="back-row" @click="closeClient()">← All clients</div>
    <div class="panel-header"><span>{{ store.treeTitle }}</span></div>
    <!-- Empty tree space is a drop target too: files land in the root -->
    <div class="tree" :class="{ 'drop-root': store.dropPath === '' }" @contextmenu="onRootCtx"
         @dragover="dragFilesOver($event, '')" @dragleave="dragFilesLeave('')" @drop="dropFilesAt($event, '')">
      <TreeNodes :nodes="store.clientTree" :ctx-menu="true" />
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.back-row {
  padding: 9px 14px; cursor: pointer; flex-shrink: 0;
  font: 500 10px var(--mono); letter-spacing: 1px; text-transform: uppercase;
  color: var(--text-4); border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px;
}
.back-row:hover { color: var(--brand); }
</style>
