<script setup>
import { store, toggleTheme } from "../store.js";
</script>

<template>
  <div id="topbar">
    <div class="logo">M</div>
    <span class="app-name">Mortgage <span class="inv">Work</span></span>
    <div class="search" v-html="store.searchLabel"></div>
    <!-- Right end of the title row: one icon, showing the theme you'd get.
         Same feather-style line set as the activity bar, currentColor so hover
         and the theme itself both just work. -->
    <span class="theme" :data-tip="store.theme === 'dark' ? 'Light theme' : 'Dark theme'"
          @click="toggleTheme()">
      <svg v-if="store.theme === 'dark'" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="4.5"/>
        <path d="M12 1.5v2M12 20.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M1.5 12h2M20.5 12h2M4.6 19.4l1.4-1.4M18 6l1.4-1.4"/>
      </svg>
      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>
      </svg>
    </span>
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
  font: 700 10px var(--mono); color: var(--on-brand);
}
#topbar .app-name { font: 700 12px var(--mono); letter-spacing: 1px; text-transform: uppercase; }
/* Inverted word: the text color *is* the background, so the letters have to be
   the page — a literal #000 would vanish on the light theme. */
#topbar .app-name .inv { background: var(--text); color: var(--bg); padding: 1px 4px; }
#topbar .search {
  /* Auto margins both sides: centers the field and pushes the toggle right */
  margin: 0 auto; width: 400px; height: 26px;
  background: var(--bg-hover); border: 1px solid var(--border);
  color: var(--text-4); font: 400 11px var(--mono); letter-spacing: .5px;
  display: flex; align-items: center; justify-content: center; gap: 8px;
}
#topbar .theme {
  width: 24px; height: 24px; flex-shrink: 0; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-4);
}
#topbar .theme svg { width: 15px; height: 15px; }
#topbar .theme:hover { color: var(--brand); background: var(--bg-hover); }
</style>
