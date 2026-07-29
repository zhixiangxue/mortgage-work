<script setup>
import { store, openCtxMenu, dragFilesOver, dragFilesLeave, dropFilesAt,
         addFilesAt, refreshWorkspace } from "../store.js";
import TreeNodes from "./TreeNodes.vue";

/* Right-click on empty space targets the library root */
function onRootCtx(e) {
  e.preventDefault();
  openCtxMenu(e, null);
}
</script>

<template>
  <div class="wrap">
    <div class="panel-header">
      Product Library
      <span class="icons">
        <span data-tip="Add docs" @click="addFilesAt('')">＋</span>
        <span data-tip="Refresh" @click="refreshWorkspace()">⟳</span>
      </span>
    </div>
    <!-- Lender docs drop straight into the library; empty space = root -->
    <div class="tree" :class="{ 'drop-root': store.dropPath === '' }" @contextmenu="onRootCtx"
         @dragover="dragFilesOver($event, '')" @dragleave="dragFilesLeave('')" @drop="dropFilesAt($event, '')">
      <TreeNodes :nodes="store.productTree" :ctx-menu="true" />
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; flex: 1; min-height: 0; }
</style>
