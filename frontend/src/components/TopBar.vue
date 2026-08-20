<script setup>
import { ref, watch, onUnmounted } from "vue";
import { store, toggleTheme, togglePanel, openUsage } from "../store.js";

const menuOpen = ref(false);

function toggleMenu() { menuOpen.value = !menuOpen.value; }

/* Close on any click outside the menu. The listener is installed only while
   the menu is open, so the opening click itself can never close it again. */
function onDocClick(e) {
  if (!e.target.closest(".acct")) menuOpen.value = false;
}
function onKeydown(e) { if (e.key === "Escape") menuOpen.value = false; }

watch(menuOpen, (open) => {
  if (open) {
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKeydown);
  } else {
    document.removeEventListener("click", onDocClick);
    document.removeEventListener("keydown", onKeydown);
  }
});
onUnmounted(() => {
  document.removeEventListener("click", onDocClick);
  document.removeEventListener("keydown", onKeydown);
});

/* Forget this machine's session and re-run boot — which lands back on the
   login screen. The reload is the simplest way to reset every panel's state
   (tabs, chat, trees) in one move. */
function logout() {
  window.pywebview.api.logout().then(() => location.reload());
}

function usage() {
  menuOpen.value = false;
  openUsage();
}
</script>

<template>
  <div id="topbar">
    <div class="logo">M</div>
    <span class="app-name">Mortgage <span class="inv">Work</span></span>
    <!-- Right end of the title row: chat-panel toggle, theme, account menu.
         The account sits at the far right, the conventional home for an
         identity control. Same feather-style line set as the activity bar,
         currentColor so hover and the theme itself both just work. -->
    <span class="tbtn first" :data-tip="store.chatVisible ? 'Hide chat panel' : 'Show chat panel'"
          @click="togglePanel('chat')">
      <!-- Layout icon: right strip fills when the panel is open, VS Code style -->
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="4.5" width="18" height="15" rx="1.5"/>
        <path v-if="!store.chatVisible" d="M15 4.5v15"/>
        <path v-else d="M15 5.5h3.5a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H15z" fill="currentColor" stroke="none"/>
      </svg>
    </span>
    <span class="tbtn" :data-tip="store.theme === 'dark' ? 'Light theme' : 'Dark theme'"
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
    <div v-if="store.user" class="acct">
      <span class="tbtn" :class="{ on: menuOpen }" :data-tip="menuOpen ? '' : 'Account'" @click.stop="toggleMenu">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="7.5" r="4"/>
          <path d="M4.5 21v-1a6 6 0 0 1 6-6h3a6 6 0 0 1 6 6v1"/>
        </svg>
      </span>
      <div v-if="menuOpen" class="acct-menu">
        <div class="acct-name">{{ store.user.name }}</div>
        <div v-if="store.user.email" class="acct-email">{{ store.user.email }}</div>
        <div class="acct-sep"></div>
        <div class="acct-item" @click="usage">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 20V10M12 20V4M6 20v-6"/>
          </svg>
          Usage
        </div>
        <div class="acct-item" @click="logout">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
            <path d="M16 17l5-5-5-5M21 12H9"/>
          </svg>
          Sign out
        </div>
      </div>
    </div>
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
#topbar .tbtn {
  width: 24px; height: 24px; flex-shrink: 0; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-4);
}
#topbar .tbtn.first { margin-left: auto; }
/* Account menu — the user icon replaces the old bare-name text; identity and
   sign-out live one click down, at the far right where an identity control
   conventionally sits (.tbtn.first pushes the whole cluster over). */
#topbar .acct { position: relative; display: flex; }
#topbar .tbtn.on { color: var(--brand); background: var(--bg-hover); }
.acct-menu {
  position: absolute; top: 34px; right: 0; z-index: 50;
  min-width: 190px; padding: 6px;
  background: var(--bg-panel); border: 1px solid var(--border);
  box-shadow: 0 8px 24px var(--shadow);
}
.acct-name {
  font: 600 12px var(--sans); color: var(--text);
  padding: 6px 8px 1px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.acct-email {
  font: 400 10.5px var(--mono); color: var(--text-4);
  padding: 1px 8px 6px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.acct-sep { height: 1px; background: var(--border); margin: 4px 0; }
.acct-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 8px; cursor: pointer;
  font: 400 11px var(--mono); color: var(--text-3);
}
.acct-item svg { width: 14px; height: 14px; flex-shrink: 0; }
.acct-item:hover { background: var(--bg-hover); color: var(--text); }
#topbar .tbtn svg { width: 15px; height: 15px; }
#topbar .tbtn:hover { color: var(--brand); background: var(--bg-hover); }
</style>
