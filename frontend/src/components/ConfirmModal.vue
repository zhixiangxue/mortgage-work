<script setup>
/* The app's own confirmation, for the few actions it can't walk back.
   Deliberately plain: a title, what will happen in words, and the button that
   does it — no native window.confirm() dialog wearing a browser's chrome. */
import { onMounted, onUnmounted } from "vue";
import { store, closeAsk, askOk } from "../store.js";

// Enter confirms, Escape cancels — a two-button dialog owes you both
function onKey(e) {
  if (!store.ask.open) return;
  if (e.key === "Escape") { e.stopPropagation(); closeAsk(); }
  else if (e.key === "Enter") { e.preventDefault(); askOk(); }
}
onMounted(() => document.addEventListener("keydown", onKey));
onUnmounted(() => document.removeEventListener("keydown", onKey));

function overlayClick(e) {
  if (e.target === e.currentTarget) closeAsk();
}
</script>

<template>
  <div id="ask-overlay" v-show="store.ask.open" @click="overlayClick">
    <div id="ask">
      <div class="a-head">{{ store.ask.title }}</div>
      <div class="a-body">{{ store.ask.body }}</div>
      <div class="a-foot">
        <button class="btn-sm" @click="closeAsk()">Cancel</button>
        <button class="btn-sm danger" @click="askOk()">{{ store.ask.label }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
#ask-overlay {
  position: fixed; inset: 0; background: var(--scrim); z-index: 400;
  display: flex; align-items: center; justify-content: center;
}
#ask { width: 400px; background: var(--bg-panel); border: 1px solid var(--border-soft); }
#ask .a-head {
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  font: 700 10px var(--mono); letter-spacing: 2px; text-transform: uppercase;
}
#ask .a-body {
  padding: 16px; font: 400 11px var(--mono); color: var(--text-3); line-height: 1.7;
}
#ask .a-foot {
  padding: 12px 16px; border-top: 1px solid var(--border);
  display: flex; gap: 8px; justify-content: flex-end;
}
#ask .btn-sm.danger { border-color: var(--red); color: var(--red); }
#ask .btn-sm.danger:hover { background: var(--red); color: var(--bg); }
</style>
