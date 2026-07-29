<script setup>
/* Singleton tooltip driven by [data-tip] via document-level delegation.
   No per-component wiring — works for static templates and v-html alike.
   IDE hover feel: first show after a delay, instant while "hot". */
import { reactive, onMounted, onUnmounted } from "vue";

const tip = reactive({ open: false, text: "", x: 0, y: 0, below: true });

let showTimer = null;
let hotUntil = 0; // moving between tipped elements keeps tooltips instant
const DELAY = 450, HOT = 300, GAP = 7;

function place(el, text) {
  const r = el.getBoundingClientRect();
  tip.below = r.bottom + 40 < window.innerHeight; // flip up near the bottom edge
  // Mono font → width is predictable; clamp so edge icons (activity bar) stay on-screen
  const w = Math.min(260, text.length * 6.3 + 18);
  tip.x = Math.min(Math.max(r.left + r.width / 2, w / 2 + 6), window.innerWidth - w / 2 - 6);
  tip.y = tip.below ? r.bottom + GAP : r.top - GAP;
}

function over(e) {
  const el = e.target.closest?.("[data-tip]");
  if (!el || !el.dataset.tip) return;
  clearTimeout(showTimer);
  const show = () => { tip.text = el.dataset.tip; place(el, tip.text); tip.open = true; };
  Date.now() < hotUntil ? show() : (showTimer = setTimeout(show, DELAY));
}

function out(e) {
  if (!e.target.closest?.("[data-tip]")) return;
  clearTimeout(showTimer);
  if (tip.open) { tip.open = false; hotUntil = Date.now() + HOT; }
}

function kill() {
  clearTimeout(showTimer);
  tip.open = false;
  hotUntil = 0; // a click ends the hover session — no instant re-show
}

onMounted(() => {
  document.addEventListener("mouseover", over);
  document.addEventListener("mouseout", out);
  document.addEventListener("mousedown", kill, true);
  document.addEventListener("scroll", kill, true);
});
onUnmounted(() => {
  document.removeEventListener("mouseover", over);
  document.removeEventListener("mouseout", out);
  document.removeEventListener("mousedown", kill, true);
  document.removeEventListener("scroll", kill, true);
});
</script>

<template>
  <Transition name="tipfade">
    <div v-if="tip.open" class="tip" :class="tip.below ? 'b' : 't'"
         :style="{ left: tip.x + 'px', top: tip.y + 'px' }">{{ tip.text }}</div>
  </Transition>
</template>

<style scoped>
.tip {
  position: fixed; z-index: 300; pointer-events: none;
  max-width: 260px; padding: 4px 8px 5px;
  font: 400 10.5px var(--mono); letter-spacing: .3px; line-height: 1.5;
  color: var(--text-2); background: var(--bg-raise);
  border: 1px solid var(--border); box-shadow: 0 4px 14px rgba(0, 0, 0, .45);
  white-space: pre-line;
}
.tip.b { transform: translateX(-50%); }
.tip.t { transform: translate(-50%, -100%); }
.tipfade-enter-active { transition: opacity .1s; }
.tipfade-enter-from { opacity: 0; }
</style>
