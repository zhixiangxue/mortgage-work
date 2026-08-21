<script setup>
import { onMounted, onUnmounted } from "vue";
import { store, pasteIntoTree, treeKeys, globalKeys } from "./store.js";
import { useResize } from "./useResize.js";
import BootOverlay from "./components/BootOverlay.vue";
import LoginScreen from "./components/LoginScreen.vue";
import TopBar from "./components/TopBar.vue";
import ActivityBar from "./components/ActivityBar.vue";
import SideBar from "./components/SideBar.vue";
import CenterArea from "./components/CenterArea.vue";
import ChatPanel from "./components/ChatPanel.vue";
import NewClientModal from "./components/NewClientModal.vue";
import ConfirmModal from "./components/ConfirmModal.vue";
import UpdatePanel from "./components/UpdatePanel.vue";
import FileHistoryPanel from "./components/FileHistoryPanel.vue";
import CtxMenu from "./components/CtxMenu.vue";
import Toast from "./components/Toast.vue";
import Tooltip from "./components/Tooltip.vue";
import SelectionBubble from "./components/SelectionBubble.vue";

// min mirrors each panel's CSS min-width. Chat width scales with screen: ~28%
// of window width, clamped between 300px and 520px, so it's comfortable on
// both wide monitors and smaller laptop screens.
const side = useResize(310, true, 220, 480);
const chatDefault = Math.max(300, Math.min(520, Math.round(window.innerWidth * 0.28)));
const chat = useResize(chatDefault, false, 300, () => window.innerWidth - 260);

// Ctrl+C/X on a tree row, Ctrl+V into a folder — either the tree's own
// clipboard or files copied in the OS file manager. globalKeys carries the
// app-level chords (Ctrl/Cmd+N → New Client).
onMounted(() => {
  document.addEventListener("paste", pasteIntoTree);
  document.addEventListener("keydown", treeKeys);
  document.addEventListener("keydown", globalKeys);
});
onUnmounted(() => {
  document.removeEventListener("paste", pasteIntoTree);
  document.removeEventListener("keydown", treeKeys);
  document.removeEventListener("keydown", globalKeys);
});
</script>

<template>
  <!-- Logged out: the login screen owns the whole window; the workspace
       shell (and its boot curtain) only exists once a session lands. -->
  <LoginScreen v-if="store.showLogin" />
  <template v-else>
    <BootOverlay />
    <TopBar />
    <div id="main">
      <ActivityBar />
      <SideBar v-show="store.sidebarVisible" :style="{ width: side.width.value + 'px' }" />
      <div class="divider" v-show="store.sidebarVisible"
           :class="{ dragging: side.dragging.value }" @pointerdown="side.start"></div>
      <CenterArea />
      <!-- The chat is fixed on the right across every view —
           chatVisible is the user's collapse/expand, nothing else hides it -->
      <div class="divider" v-show="store.chatVisible"
           :class="{ dragging: chat.dragging.value }" @pointerdown="chat.start"></div>
      <ChatPanel v-show="store.chatVisible" :style="{ width: chat.width.value + 'px' }" />
    </div>
    <FileHistoryPanel />
    <NewClientModal />
    <ConfirmModal />
    <UpdatePanel />
  </template>
  <Toast />
  <CtxMenu />
  <Tooltip />
  <SelectionBubble />
</template>

<style scoped>
#main { flex: 1; display: flex; min-height: 0; }
/* The grab zone stays a comfortable 4px (+ ::after wings), but the visible
   highlight is a slim inset stripe that fades out at both ends — a full-width
   edge-to-edge brand bar read as chunky. The stripe lives on ::before so the
   fade can animate opacity: gradients can't transition, backgrounds snap. */
.divider { width: 4px; cursor: col-resize; flex-shrink: 0; position: relative; z-index: 5; }
.divider::before {
  content: ""; position: absolute; top: 0; bottom: 0; left: 1.25px; right: 1.25px;
  background: linear-gradient(to bottom, transparent, var(--divider-hint) 32%, var(--divider-hint) 68%, transparent);
  opacity: 0; transition: opacity .15s; pointer-events: none;
}
/* Invisible grab zone wider than the 4px stripe — a hairline target is half
   the reason dragging felt hit-or-miss */
.divider::after { content: ""; position: absolute; top: 0; bottom: 0; left: -3px; right: -3px; cursor: col-resize; }
.divider:hover::before { opacity: 1; }
/* Same specificity as :hover — keep it later so the drag stripe wins */
.divider.dragging::before {
  opacity: 1;
  background: linear-gradient(to bottom, transparent, var(--divider-grip) 32%, var(--divider-grip) 68%, transparent);
}
</style>
