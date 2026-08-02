<script setup>
/* Recursive tree renderer — replaces the old renderTree() string builder.
   Dir open/collapse is node state (n.open); files open docs or toast.
   OS file drags land here too: dirs take the drop themselves, files hand
   it to their parent dir — IDE convention. */
import {
  store, openTreeFile, openCtxMenu,
  dragFilesOver, dragFilesLeave, dropFilesAt, TREE_MIME,
  commitRename, cancelRename, isCut, retryIndexing,
} from "../store.js";

const props = defineProps({
  nodes: { type: Array, required: true },
  depth: { type: Number, default: 0 },
  base: { type: String, default: "" },
  ctxMenu: { type: Boolean, default: false }, // client tree only
});

const badgeLabel = t => (["pdf", "md", "yml", "eml", "img", "txt", "ai"].includes(t) ? t : "md");

function openFile(n, path) {
  openTreeFile(n, path);
}

function onCtx(e, n, path) {
  if (!props.ctxMenu) return;
  e.preventDefault();
  e.stopPropagation();
  openCtxMenu(e, { path, type: n.type === "dir" ? "dir" : "file" });
}

// Two payloads: text/plain feeds the composer pill, TREE_MIME enables
// dropping back onto the tree as a move (folders get a trailing slash)
function dragPayload(e, n, path) {
  e.dataTransfer.setData("text/plain", n.type === "dir" ? n.name + "/" : n.name);
  e.dataTransfer.setData(TREE_MIME, path);
}

// A dir toggles AND becomes the paste target; parent path for file rows
function clickDir(n, path) {
  n.open = !n.open;
  store.selectedPath = path;
}
const parentPath = () => (props.base ? props.base.slice(0, -1) : "");

// Inline rename: focus and pre-select the basename (ext stays put)
const vRenameFocus = {
  mounted(el) {
    el.focus();
    const dot = el.value.lastIndexOf(".");
    el.setSelectionRange(0, dot > 0 ? dot : el.value.length);
  },
};
</script>

<template>
  <template v-for="n in nodes" :key="base + n.name">
    <template v-if="n.type === 'dir'">
      <div class="node" :class="{ collapsed: !n.open, selected: store.selectedPath === base + n.name,
                                  'drop-target': store.dropPath === base + n.name,
                                  cut: isCut(base + n.name) }"
           :draggable="store.renamingPath !== base + n.name"
           :style="{ paddingLeft: 8 + depth * 14 + 'px' }"
           @dragstart="dragPayload($event, n, base + n.name)"
           @dragover="dragFilesOver($event, base + n.name)"
           @dragleave="dragFilesLeave(base + n.name)"
           @drop="dropFilesAt($event, base + n.name)"
           @click="clickDir(n, base + n.name)"
           @contextmenu="onCtx($event, n, base + n.name)">
        <span class="arrow">▼</span>
        <input v-if="store.renamingPath === base + n.name" class="rename-input" :value="n.name" v-rename-focus
               @click.stop @keydown.enter="commitRename(base + n.name, $event.target.value)"
               @keydown.esc="cancelRename()" @blur="commitRename(base + n.name, $event.target.value)" />
        <span v-else class="folder-name" :class="n.git || ''">{{ n.name }}/</span>
      </div>
      <div class="children" v-show="n.open">
        <TreeNodes :nodes="n.children || []" :depth="depth + 1" :base="base + n.name + '/'" :ctx-menu="ctxMenu" />
      </div>
    </template>
    <div v-else class="node" :class="{ selected: store.selectedPath === base + n.name,
                                       cut: isCut(base + n.name) }"
         :draggable="store.renamingPath !== base + n.name"
         :style="{ paddingLeft: 8 + depth * 14 + 14 + 'px' }"
         @dragstart="dragPayload($event, n, base + n.name)"
         @dragover="dragFilesOver($event, parentPath())"
         @dragleave="dragFilesLeave(parentPath())"
         @drop="dropFilesAt($event, parentPath())"
         @click.stop="openFile(n, base + n.name)"
         @contextmenu="onCtx($event, n, base + n.name)">
      <!-- Indexing marker before the badge: spinner = in flight, bang = failed -->
      <span v-if="n.idx === 'indexing'" class="idx-spin" title="Indexing…"></span>
      <span v-else-if="n.idx === 'failed'" class="idx-bang"
            title="Indexing failed — click to retry"
            @click.stop="retryIndexing()">!</span>
      <span class="fbadge" :class="badgeLabel(n.type)">{{ badgeLabel(n.type).toUpperCase() }}</span>
      <input v-if="store.renamingPath === base + n.name" class="rename-input" :value="n.name" v-rename-focus
             @click.stop @keydown.enter="commitRename(base + n.name, $event.target.value)"
             @keydown.esc="cancelRename()" @blur="commitRename(base + n.name, $event.target.value)" />
      <span v-else class="fname" :class="n.git || ''">{{ n.name }}</span>
      <!-- Right-side marker: git change letter (U/M) only -->
      <span v-if="n.git === 'new'" class="gletter new">U</span>
      <span v-else-if="n.git === 'mod'" class="gletter mod">M</span>
    </div>
  </template>
</template>
