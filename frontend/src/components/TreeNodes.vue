<script setup>
/* Recursive tree renderer — replaces the old renderTree() string builder.
   Dir open/collapse is node state (n.open); files open docs or toast.
   OS file drags land here too: dirs take the drop themselves, files hand
   it to their parent dir — IDE convention. */
import {
  store, openTreeFile, openCtxMenu,
  dragFilesOver, dragFilesLeave, dropFilesAt, TREE_MIME,
  commitRename, cancelRename, isCut,
  isSel, setSel, toggleSel, rangeSel, dragSelection,
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
// dropping back onto the tree as a move (folders get a trailing slash).
// A drag starting inside a multi-selection carries the whole set as
// {paths:[…]} JSON — both drop sides (tree move, chat pills) speak it.
function dragPayload(e, n, path) {
  const sel = dragSelection(path);
  if (sel.length > 1) {
    e.dataTransfer.setData("text/plain",
      sel.map(s => s.dir ? s.name + "/" : s.name).join("\n"));
    e.dataTransfer.setData(TREE_MIME, JSON.stringify({ paths: sel }));
  } else {
    e.dataTransfer.setData("text/plain", n.type === "dir" ? n.name + "/" : n.name);
    e.dataTransfer.setData(TREE_MIME, path);
  }
}

// Explorer click grammar: plain click is single-select (dirs also toggle,
// files also open); Ctrl adds/removes without side effects; Shift extends a
// range from the anchor.
function clickDir(e, n, path) {
  if (e.ctrlKey || e.metaKey) { toggleSel(path); return; }
  if (e.shiftKey) { rangeSel(path); return; }
  n.open = !n.open;
  setSel(path);
}

function clickFile(e, n, path) {
  if (e.ctrlKey || e.metaKey) { toggleSel(path); return; }
  if (e.shiftKey) { rangeSel(path); return; }
  openFile(n, path);
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
      <div class="node" :class="{ collapsed: !n.open, selected: isSel(base + n.name),
                                  'drop-target': store.dropPath === base + n.name,
                                  cut: isCut(base + n.name) }"
           :draggable="store.renamingPath !== base + n.name"
           :style="{ paddingLeft: 8 + depth * 14 + 'px' }"
           @dragstart="dragPayload($event, n, base + n.name)"
           @dragover="dragFilesOver($event, base + n.name)"
           @dragleave="dragFilesLeave(base + n.name)"
           @drop="dropFilesAt($event, base + n.name)"
           @click="clickDir($event, n, base + n.name)"
           @contextmenu="onCtx($event, n, base + n.name)">
        <span class="arrow">▼</span>
        <!-- Agent activity dot: blue pulse = organizer running -->
        <span v-if="depth === 0 && store.organizer.running"
              class="agent-dot working" />
        <input v-if="store.renamingPath === base + n.name" class="rename-input" :value="n.name" v-rename-focus
               @click.stop @keydown.enter="commitRename(base + n.name, $event.target.value)"
               @keydown.esc="cancelRename()" @blur="commitRename(base + n.name, $event.target.value)" />
        <span v-else class="folder-name" :class="n.git || ''">{{ n.name }}/</span>
      </div>
      <div class="children" v-show="n.open">
        <TreeNodes :nodes="n.children || []" :depth="depth + 1" :base="base + n.name + '/'" :ctx-menu="ctxMenu" />
      </div>
    </template>
    <div v-else class="node" :class="{ selected: isSel(base + n.name),
                                       cut: isCut(base + n.name) }"
         :draggable="store.renamingPath !== base + n.name"
         :style="{ paddingLeft: 8 + depth * 14 + 14 + 'px' }"
         @dragstart="dragPayload($event, n, base + n.name)"
         @dragover="dragFilesOver($event, parentPath())"
         @dragleave="dragFilesLeave(parentPath())"
         @drop="dropFilesAt($event, parentPath())"
         @click.stop="clickFile($event, n, base + n.name)"
         @contextmenu="onCtx($event, n, base + n.name)">
      <!-- File-type badge — indexing status lives in the Knowledge Base
           panel now, the tree stays a plain file tree. -->
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
