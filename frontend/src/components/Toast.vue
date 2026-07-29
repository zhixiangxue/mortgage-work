<script setup>
import { store } from "../store.js";
</script>

<template>
  <div id="toast" :class="{ show: store.toast.show }">{{ store.toast.msg }}</div>
</template>

<style scoped>
#toast {
  position: fixed; bottom: 40px; left: 50%; transform: translateX(-50%);
  background: var(--bg-raise); border: 1px solid var(--border-soft);
  box-shadow: inset 2px 0 0 var(--brand);
  color: var(--text-2); font: 400 11px var(--mono); padding: 8px 16px;
  opacity: 0; pointer-events: none; transition: opacity .2s; z-index: 999;
}
#toast.show { opacity: 1; }
</style>
