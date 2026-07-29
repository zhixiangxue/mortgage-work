<script setup>
import { ref, watch, nextTick, onMounted, onUnmounted } from "vue";
import { store, hideCtx, ctxAction } from "../store.js";

const menuEl = ref(null);
const pos = ref({ left: 0, top: 0 });

// Clamp to the viewport so the menu never runs off-screen
watch(() => [store.ctx.open, store.ctx.x, store.ctx.y], async ([open]) => {
  if (!open) return;
  pos.value = { left: store.ctx.x, top: store.ctx.y };
  await nextTick();
  const mw = menuEl.value.offsetWidth, mh = menuEl.value.offsetHeight;
  pos.value = {
    left: Math.min(store.ctx.x, innerWidth - mw - 6),
    top: Math.min(store.ctx.y, innerHeight - mh - 6),
  };
});

const onDocClick = () => hideCtx();
const onKey = e => { if (e.key === "Escape") hideCtx(); };
onMounted(() => {
  document.addEventListener("click", onDocClick);
  document.addEventListener("keydown", onKey);
});
onUnmounted(() => {
  document.removeEventListener("click", onDocClick);
  document.removeEventListener("keydown", onKey);
});
</script>

<template>
  <div id="ctx-menu" ref="menuEl" v-show="store.ctx.open"
       :style="{ left: pos.left + 'px', top: pos.top + 'px' }">
    <template v-for="(it, i) in store.ctx.items" :key="i">
      <div v-if="it" class="ctx-item" :class="{ danger: it[0].startsWith('delete') }" @click="ctxAction(it[0])">{{ it[1] }}</div>
      <div v-else class="ctx-sep"></div>
    </template>
  </div>
</template>

<style scoped>
#ctx-menu {
  position: fixed; z-index: 300; min-width: 200px; padding: 4px 0;
  background: var(--bg-panel); border: 1px solid var(--border-soft);
  box-shadow: 0 8px 24px var(--shadow);
}
.ctx-item {
  padding: 6px 14px; font: 400 11px var(--mono); color: var(--text-2);
  cursor: pointer; display: flex; align-items: center; justify-content: space-between; gap: 16px;
}
.ctx-item:hover { background: var(--bg-hover); color: var(--text); }
.ctx-item.danger:hover { background: var(--bg-hover); color: var(--red); }
.ctx-sep { height: 1px; background: var(--border); margin: 4px 0; }
</style>
