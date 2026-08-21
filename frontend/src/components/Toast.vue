<script setup>
import { store, hideToast } from "../store.js";

/* Action link (optional): clicking it runs the bound handler and dismisses
   the toast — the announcement hands the user straight to the surface it
   was talking about. */
function act() {
  const a = store.toast.action;
  hideToast();
  if (a && a.run) a.run();
}
</script>

<template>
  <div id="toast" :class="{ show: store.toast.show }">
    {{ store.toast.msg }}
    <a v-if="store.toast.action" class="toast-act" @click="act">{{ store.toast.action.label }}</a>
  </div>
</template>

<style scoped>
#toast {
  position: fixed; bottom: 40px; left: 50%; transform: translateX(-50%);
  background: var(--bg-raise); border: 1px solid var(--border-soft);
  box-shadow: inset 2px 0 0 var(--brand);
  color: var(--text-2); font: 400 11px var(--mono); padding: 8px 16px;
  opacity: 0; pointer-events: none; transition: opacity .2s; z-index: 999;
}
#toast.show { opacity: 1; pointer-events: auto; }
.toast-act {
  margin-left: 12px; color: var(--brand); cursor: pointer;
  text-decoration: underline; text-underline-offset: 2px;
}
.toast-act:hover { filter: brightness(1.2); }
</style>
