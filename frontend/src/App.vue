<script setup>
import { onMounted, onUnmounted } from "vue";
import { store, pasteIntoTree, treeKeys } from "./store.js";
import { useResize } from "./useResize.js";
import BootOverlay from "./components/BootOverlay.vue";
import TopBar from "./components/TopBar.vue";
import ActivityBar from "./components/ActivityBar.vue";
import SideBar from "./components/SideBar.vue";
import CenterArea from "./components/CenterArea.vue";
import ChatPanel from "./components/ChatPanel.vue";
import NewClientModal from "./components/NewClientModal.vue";
import ConfirmModal from "./components/ConfirmModal.vue";
import FileHistoryPanel from "./components/FileHistoryPanel.vue";
import CtxMenu from "./components/CtxMenu.vue";
import Toast from "./components/Toast.vue";
import Tooltip from "./components/Tooltip.vue";

const side = useResize(310, true);
const chat = useResize(380, false);

// Ctrl+C/X on a tree row, Ctrl+V into a folder — either the tree's own
// clipboard or files copied in the OS file manager
onMounted(() => {
  document.addEventListener("paste", pasteIntoTree);
  document.addEventListener("keydown", treeKeys);
});
onUnmounted(() => {
  document.removeEventListener("paste", pasteIntoTree);
  document.removeEventListener("keydown", treeKeys);
});
</script>

<template>
  <BootOverlay />
  <TopBar />
  <div id="main">
    <ActivityBar />
    <SideBar v-show="store.sidebarVisible" :style="{ width: side.width.value + 'px' }" />
    <div class="divider" v-show="store.sidebarVisible"
         :class="{ dragging: side.dragging.value }" @mousedown="side.start"></div>
    <CenterArea />
    <!-- Runtime is a developer view — no assistant chat there, just the console -->
    <div class="divider" v-show="store.chatVisible && store.view !== 'agent'"
         :class="{ dragging: chat.dragging.value }" @mousedown="chat.start"></div>
    <ChatPanel v-show="store.chatVisible && store.view !== 'agent'" :style="{ width: chat.width.value + 'px' }" />
  </div>
  <Toast />
  <CtxMenu />
  <Tooltip />
  <FileHistoryPanel />
  <NewClientModal />
  <ConfirmModal />
</template>

<style scoped>
#main { flex: 1; display: flex; min-height: 0; }
.divider { width: 4px; cursor: col-resize; flex-shrink: 0; background: transparent; transition: background .15s; }
.divider:hover, .divider.dragging { background: var(--brand); }
</style>
