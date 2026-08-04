<script setup>
import {
  store, closeClient, openCtxMenu, dragFilesOver, dragFilesLeave, dropFilesAt,
  showFolderHint, dismissFolderHint, visibleClientTree,
} from "../store.js";
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
    <!-- One-time hint: the scaffolded folders are suggestions, not constraints.
         Dismissed per-client via localStorage; auto-hides once files arrive. -->
    <div v-if="showFolderHint()" class="hint-banner">
      <span class="hint-text">These folders are <b>suggestions</b> — rename, delete, or reorganize freely. Drop files anywhere.</span>
      <span class="hint-dismiss" @click="dismissFolderHint()">✕</span>
    </div>
    <!-- Empty tree space is a drop target too: files land in the root.
         client.yaml is hidden: it is machine-managed, the Edit Client modal is its UI. -->
    <div class="tree" :class="{ 'drop-root': store.dropPath === '' }" @contextmenu="onRootCtx"
         @dragover="dragFilesOver($event, '')" @dragleave="dragFilesLeave('')" @drop="dropFilesAt($event, '')">
      <TreeNodes :nodes="visibleClientTree()" :ctx-menu="true" />
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
.hint-banner {
  padding: 8px 14px; background: var(--wash-brand);
  border-bottom: 1px solid var(--border);
  font: 400 11px var(--sans); color: var(--text-3); line-height: 1.5;
  display: flex; align-items: flex-start; gap: 8px; flex-shrink: 0;
}
.hint-text { flex: 1; }
.hint-text b { color: var(--brand); font-weight: 600; }
.hint-dismiss {
  cursor: pointer; color: var(--text-4); font-size: 13px; flex-shrink: 0;
  line-height: 1; padding: 1px 2px;
}
.hint-dismiss:hover { color: var(--text); }
</style>
