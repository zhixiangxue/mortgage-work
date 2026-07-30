<script setup>
/* IDE-style "selection → chat" affordance: select text in any document pane
   and a small bubble offers to quote it into the composer. Document panes
   only (#doc-area / .file-pane) — selecting inside chat or UI chrome must
   not trigger it. */
import { reactive, onMounted, onUnmounted } from "vue";
import { store, docs, focusChat } from "../store.js";
import { insertQuotePill } from "../utils.js";

const bub = reactive({ show: false, x: 0, y: 0, text: "" });

const PANES = "#doc-area, .file-pane";

function onMouseUp(e) {
  // The bubble handles its own click; don't re-evaluate the selection under it
  if (e.target.closest && e.target.closest("#sel-bubble")) return;
  const mx = e.clientX, my = e.clientY;
  // Post-mouseup tick: WebKit finalizes the selection after the event fires
  setTimeout(() => {
    const sel = window.getSelection();
    const text = sel ? String(sel).trim() : "";
    if (!text || sel.isCollapsed) { bub.show = false; return; }
    const anchor = sel.anchorNode instanceof Element ? sel.anchorNode : sel.anchorNode?.parentElement;
    if (!anchor || !anchor.closest(PANES)) { bub.show = false; return; }
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    if (!rect.width && !rect.height) { bub.show = false; return; }
    bub.text = text;
    // Just below-right of where the mouse was released — that's where the
    // hand already is after a left-to-right drag; clamped to the viewport
    bub.x = Math.min(mx + 6, window.innerWidth - 130);
    bub.y = Math.min(my + 14, window.innerHeight - 40);
    bub.show = true;
  }, 0);
}

function addToContext() {
  const text = bub.text;
  bub.show = false;
  window.getSelection()?.removeAllRanges();
  // Provenance: every doc's crumb is [scope, ...tree path], so the quote
  // carries which file it came from, not just the words
  const d = docs[store.active];
  const addr = d && d.crumb ? { scope: d.crumb[0], path: d.crumb.slice(1).join("/") } : null;
  focusChat();                    // opens the chat panel if it's hidden
  // insertQuotePill needs the composer in the DOM — focusChat defers via rAF
  requestAnimationFrame(() => insertQuotePill(text, addr));
}

function dismiss(e) {
  if (e.target.closest && e.target.closest("#sel-bubble")) return;
  bub.show = false;
}

// Scrolling moves the selection out from under the bubble — just drop it
const onScroll = () => { bub.show = false; };

onMounted(() => {
  document.addEventListener("mouseup", onMouseUp);
  document.addEventListener("mousedown", dismiss);
  document.addEventListener("scroll", onScroll, true);
});
onUnmounted(() => {
  document.removeEventListener("mouseup", onMouseUp);
  document.removeEventListener("mousedown", dismiss);
  document.removeEventListener("scroll", onScroll, true);
});
</script>

<template>
  <div v-show="bub.show" id="sel-bubble" :style="{ left: bub.x + 'px', top: bub.y + 'px' }"
       @mousedown.prevent @click="addToContext">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
    Add to chat
  </div>
</template>

<style scoped>
#sel-bubble {
  position: fixed; z-index: 300;
  display: flex; align-items: center; gap: 6px;
  padding: 5px 10px; cursor: pointer;
  background: var(--bg-panel); border: 1px solid var(--border-soft);
  box-shadow: 0 4px 14px var(--shadow);
  font: 500 10.5px var(--mono); letter-spacing: .5px; color: var(--text-2);
  user-select: none; white-space: nowrap;
}
#sel-bubble:hover { color: var(--brand); border-color: var(--brand); }
#sel-bubble svg { width: 12px; height: 12px; }
</style>
