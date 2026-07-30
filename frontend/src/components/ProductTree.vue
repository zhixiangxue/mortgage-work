<script setup>
import { ref, computed } from "vue";
import { store, openCtxMenu, dragFilesOver, dragFilesLeave, dropFilesAt,
         addFilesAt, refreshWorkspace, openTreeFile } from "../store.js";
import TreeNodes from "./TreeNodes.vue";

/* Right-click on empty space targets the library root */
function onRootCtx(e) {
  e.preventDefault();
  openCtxMenu(e, null);
}

/* Filename filter — the product library spans many lenders, so typing flattens
   the tree into just the files whose name matches, each tagged with its lender
   folder. Empty query falls straight back to the normal tree. */
const query = ref("");
const badgeLabel = t => (["pdf", "md", "yml", "eml", "img", "txt", "ai"].includes(t) ? t : "md");

function collect(nodes, base, out) {
  for (const n of nodes) {
    const path = base + n.name;
    if (n.type === "dir") collect(n.children || [], path + "/", out);
    else out.push({ node: n, name: n.name, type: n.type, path, dir: base.replace(/\/$/, "") });
  }
  return out;
}

const hits = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return [];
  return collect(store.productTree, "", []).filter(h => h.name.toLowerCase().includes(q));
});
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
    <div class="filter">
      <svg class="fic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
           stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
      <input v-model="query" placeholder="Filter files by name…" spellcheck="false" @keydown.esc="query = ''" />
      <button v-if="query" class="fclear" data-tip="Clear" @click="query = ''">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
             stroke-linecap="round" stroke-linejoin="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
      </button>
    </div>
    <!-- Query active: flat filename matches across every lender -->
    <div v-if="query.trim()" class="tree hits">
      <div v-if="!hits.length" class="no-hits">No files match “{{ query.trim() }}”</div>
      <div v-for="h in hits" :key="h.path" class="node" @click="openTreeFile(h.node, h.path)">
        <span class="fbadge" :class="badgeLabel(h.type)">{{ badgeLabel(h.type).toUpperCase() }}</span>
        <span class="fname">{{ h.name }}</span>
        <span v-if="h.dir" class="hit-dir">{{ h.dir }}</span>
      </div>
    </div>
    <!-- Lender docs drop straight into the library; empty space = root -->
    <div v-else class="tree" :class="{ 'drop-root': store.dropPath === '' }" @contextmenu="onRootCtx"
         @dragover="dragFilesOver($event, '')" @dragleave="dragFilesLeave('')" @drop="dropFilesAt($event, '')">
      <TreeNodes :nodes="store.productTree" :ctx-menu="true" />
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.filter { display: flex; align-items: center; gap: 6px; padding: 0 10px 8px; flex-shrink: 0; }
.filter .fic { width: 13px; height: 13px; color: var(--text-4); flex-shrink: 0; }
.filter input {
  flex: 1; min-width: 0; height: 24px; padding: 0 6px;
  background: var(--bg-hover); border: 1px solid var(--border);
  color: var(--text); font: 400 12px var(--mono); outline: none;
}
.filter input:focus { border-color: var(--border-soft); }
.filter input::placeholder { color: var(--text-4); }
.filter .fclear {
  display: flex; background: none; border: none; cursor: pointer;
  color: var(--text-4); padding: 2px; flex-shrink: 0;
}
.filter .fclear:hover { color: var(--text-2); }
.filter .fclear svg { width: 12px; height: 12px; }
/* Flat result rows reuse the tree's .node/.fbadge/.fname; they just need a
   left inset (tree rows get theirs from a depth-based inline style) and a dim
   trailing lender path so the same filename under two lenders stays legible. */
.hits .node { padding-left: 10px; }
.hit-dir {
  margin-left: auto; padding-left: 10px;
  color: var(--text-4); font: 400 11px var(--mono);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 45%;
}
.no-hits { padding: 10px 12px; color: var(--text-4); font: 400 11px var(--mono); }
</style>
