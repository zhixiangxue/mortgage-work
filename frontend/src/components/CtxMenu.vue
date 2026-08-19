<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from "vue";
import { store, hideCtx, ctxAction } from "../store.js";

const menuEl = ref(null);
const subEl = ref(null);
const pos = ref({ left: 0, top: 0 });

// Submenu state: which parent item is hovered and where the flyout sits.
// The rect comes from the parent row itself, so the flyout hugs its edge.
const sub = ref(-1);
const subPos = ref({ left: 0, top: 0 });
const subItems = computed(() => {
  const it = store.ctx.items && store.ctx.items[sub.value];
  return it && it[2] ? it[2] : [];
});

async function openSub(i, e) {
  sub.value = i;
  const r = e.currentTarget.getBoundingClientRect();
  await nextTick();
  const sw = subEl.value ? subEl.value.offsetWidth : 180;
  // Flip to the left side when there's no room on the right
  const left = r.right + sw + 8 > innerWidth ? r.left - sw - 2 : r.right + 2;
  subPos.value = { left, top: Math.min(r.top - 5, innerHeight - (subEl.value ? subEl.value.offsetHeight : 0) - 6) };
}

// Clamp to the viewport so the menu never runs off-screen
watch(() => [store.ctx.open, store.ctx.x, store.ctx.y], async ([open]) => {
  if (!open) return;
  sub.value = -1;
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
      <!-- Parent of a flyout: hover expands, a click does nothing -->
      <div v-if="it && it[2]" class="ctx-item has-sub" :class="{ open: sub === i }"
           @mouseenter="openSub(i, $event)" @click.stop>
        {{ it[1] }}
        <svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
      </div>
      <div v-else-if="it" class="ctx-item" :class="{ danger: it[0].startsWith('delete') }"
           @mouseenter="sub = -1" @click="ctxAction(it[0])">{{ it[1] }}</div>
      <div v-else class="ctx-sep" @mouseenter="sub = -1"></div>
    </template>
    <!-- Flyout: the current entry gets a check, so "where is it now" is obvious -->
    <div v-if="sub >= 0 && subItems.length" ref="subEl" class="ctx-sub"
         :style="{ left: subPos.left + 'px', top: subPos.top + 'px' }">
      <div v-for="(s, j) in subItems" :key="j" class="ctx-item"
           :class="{ active: s[0] === store.ctx.current }" @click="ctxAction(s[0])">
        <svg v-if="s[0] === store.ctx.current" viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
        <span v-else class="check-ph"></span>
        {{ s[1] }}
      </div>
    </div>
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
.ctx-item.has-sub svg { color: var(--text-4); flex-shrink: 0; }
.ctx-item.has-sub.open { background: var(--bg-hover); color: var(--text); }
.ctx-sep { height: 1px; background: var(--border); margin: 4px 0; }
/* Flyout panel — same chrome as the menu it hangs off */
.ctx-sub {
  position: fixed; z-index: 301; min-width: 170px; padding: 4px 0;
  background: var(--bg-panel); border: 1px solid var(--border-soft);
  box-shadow: 0 8px 24px var(--shadow);
}
.ctx-sub .ctx-item { gap: 8px; justify-content: flex-start; }
.ctx-sub .ctx-item svg { color: var(--brand); flex-shrink: 0; }
.ctx-sub .ctx-item .check-ph { width: 10px; flex-shrink: 0; }
.ctx-sub .ctx-item.active { color: var(--text); }
</style>
