<script setup>
import { store } from "../store.js";
</script>

<template>
  <div id="topbar">
    <div class="logo">M</div>
    <span class="app-name">Mortgage <span class="inv">Work</span></span>
    <div class="search" v-html="store.searchLabel"></div>
  </div>
</template>

<style scoped>
#topbar {
  height: 40px; background: var(--bg);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center;
  padding: 0 14px; gap: 10px;
  flex-shrink: 0; user-select: none;
}
#topbar .logo {
  width: 20px; height: 20px; background: var(--brand);
  display: flex; align-items: center; justify-content: center;
  font: 700 10px var(--mono); color: #000;
}
#topbar .app-name { font: 700 12px var(--mono); letter-spacing: 1px; text-transform: uppercase; }
#topbar .app-name .inv { background: var(--text); color: #000; padding: 1px 4px; }
#topbar .search {
  margin: 0 auto; width: 400px; height: 26px;
  background: var(--bg-hover); border: 1px solid var(--border);
  color: var(--text-4); font: 400 11px var(--mono); letter-spacing: .5px;
  display: flex; align-items: center; justify-content: center; gap: 8px;
}
</style>
