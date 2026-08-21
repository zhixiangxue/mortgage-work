<script setup>
import { ref, watch, onUnmounted } from "vue";
import { store, toggleTheme, togglePanel, openUsage, openPlan, setFontScale } from "../store.js";

const menuOpen = ref(false);
const fontOpen = ref(false);

function toggleMenu() { menuOpen.value = !menuOpen.value; fontOpen.value = false; }
function toggleFont() { fontOpen.value = !fontOpen.value; menuOpen.value = false; }
function onFsInput(e) { setFontScale(+e.target.value / 100); }

/* Close on any click outside the menu. The listener is installed only while
   the menu is open, so the opening click itself can never close it again. */
function onDocClick(e) {
  if (!e.target.closest(".acct")) menuOpen.value = false;
}
function onKeydown(e) { if (e.key === "Escape") menuOpen.value = false; }

/* Same pattern for the text-size popover — its own listener so each panel
   only answers to clicks outside itself. */
function onFontDocClick(e) {
  if (!e.target.closest(".fsize")) fontOpen.value = false;
}
function onFontKey(e) { if (e.key === "Escape") fontOpen.value = false; }

watch(menuOpen, (open) => {
  if (open) {
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKeydown);
  } else {
    document.removeEventListener("click", onDocClick);
    document.removeEventListener("keydown", onKeydown);
  }
});
watch(fontOpen, (open) => {
  if (open) {
    document.addEventListener("click", onFontDocClick);
    document.addEventListener("keydown", onFontKey);
  } else {
    document.removeEventListener("click", onFontDocClick);
    document.removeEventListener("keydown", onFontKey);
  }
});
onUnmounted(() => {
  document.removeEventListener("click", onDocClick);
  document.removeEventListener("keydown", onKeydown);
  document.removeEventListener("click", onFontDocClick);
  document.removeEventListener("keydown", onFontKey);
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

/* Single home for subscription changes — redemption codes today, downgrades
   and billing later. Every plan entry point in the app opens this tab. */
function plan() {
  menuOpen.value = false;
  openPlan();
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
    <!-- Text size: the LO audience skews older, so global zoom sits one click
         away. The popover's slider rides store.fontScale, persisted via the
         work-repo session. -->
    <div class="fsize">
      <span class="tbtn" :class="{ on: fontOpen }" :data-tip="fontOpen ? '' : 'Text size'"
            @click.stop="toggleFont">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 18.5 L9.25 5.5 L14.5 18.5 M6.1 13.8 H12.4"/>
          <path d="M15.5 18.5 l3.25-8 l3.25 8 M16.9 15.9 H20.6"/>
        </svg>
      </span>
      <div v-if="fontOpen" class="fs-pop" @click.stop>
        <div class="fs-head">
          <span class="fs-label">Text size</span>
          <!-- Clicking the readout snaps back to 100% -->
          <span class="fs-val" :class="{ def: store.fontScale === 1 }"
                @click="setFontScale(1)" data-tip="Reset to 100%">{{ Math.round(store.fontScale * 100) }}%</span>
        </div>
        <div class="fs-row">
          <svg class="fs-a sm" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 19 L12 5 L19 19 M7.8 14 H16.2"/>
          </svg>
          <input class="fs-slider" type="range" min="90" max="130" step="5"
                 :value="Math.round(store.fontScale * 100)" @input="onFsInput">
          <svg class="fs-a lg" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 19 L12 5 L19 19 M7.8 14 H16.2"/>
          </svg>
        </div>
      </div>
    </div>
    <div v-if="store.user" class="acct">
      <span class="tbtn" :class="{ on: menuOpen }" :data-tip="menuOpen ? '' : 'Account'" @click.stop="toggleMenu">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="7.5" r="4"/>
          <path d="M4.5 21v-1a6 6 0 0 1 6-6h3a6 6 0 0 1 6 6v1"/>
        </svg>
      </span>
      <div v-if="menuOpen" class="acct-menu">
        <div class="acct-name">
          <span class="acct-nm">{{ store.user.name }}</span>
          <!-- Read-only tier badge. Upgrade paths live elsewhere; the plan
               may grow its own page later, so nothing links off this pill. -->
          <span v-if="store.plan" class="plan-pill" :class="store.plan">{{ store.plan.toUpperCase() }}</span>
        </div>
        <div v-if="store.user.email" class="acct-email">{{ store.user.email }}</div>
        <div class="acct-sep"></div>
        <div class="acct-item" @click="usage">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 20V10M12 20V4M6 20v-6"/>
          </svg>
          Usage
        </div>
        <div class="acct-item" @click="plan">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>
          </svg>
          Plan
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
  display: flex; align-items: center; gap: 7px;
  font: 600 12px var(--sans); color: var(--text);
  padding: 6px 8px 1px;
}
.acct-name .acct-nm {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* Read-only plan badge: Pro wears the brand color quietly, Free stays a
   neutral amber — both purely informational, nothing links off them. */
.plan-pill {
  flex: none; font: 700 8px var(--mono); letter-spacing: 1px;
  padding: 2px 6px; border: 1px solid var(--border);
}
.plan-pill.pro { color: var(--brand); border-color: var(--brand); }
.plan-pill.free { color: var(--amber); border-color: var(--amber); }
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

/* Text-size popover — same visual family as the account menu */
.fsize { position: relative; display: flex; }
.fs-pop {
  position: absolute; top: 34px; right: 0; z-index: 50;
  width: 210px; padding: 10px 12px;
  background: var(--bg-panel); border: 1px solid var(--border);
  box-shadow: 0 8px 24px var(--shadow);
}
.fs-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 8px; }
.fs-label { font: 600 11px var(--mono); color: var(--text-3); text-transform: uppercase; letter-spacing: .5px; }
/* The readout doubles as the reset — only highlighted when off 100% */
.fs-val { font: 600 12px var(--mono); color: var(--brand); cursor: pointer; }
.fs-val.def { color: var(--text-4); cursor: default; }
.fs-row { display: flex; align-items: center; gap: 8px; }
.fs-a { color: var(--text-4); flex-shrink: 0; }
.fs-a.sm { width: 10px; height: 10px; }
.fs-a.lg { width: 16px; height: 16px; }
/* Slim slider to match the app's thin scrollbars; WebKit-native pseudo styling */
.fs-slider {
  -webkit-appearance: none; appearance: none;
  flex: 1; height: 3px; background: var(--border-soft); outline: none; cursor: pointer;
}
.fs-slider::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 12px; height: 12px; background: var(--brand); cursor: pointer;
}
.fs-slider::-webkit-slider-thumb:hover { background: var(--green); }
</style>
