<script setup>
/* Real conversation list from the agent's `list` reply ({id,title,updated});
   clicking a row opens that conversation over the WS. */
import { ref, onMounted, onUnmounted } from "vue";
import { store, showToast } from "../store.js";
import { openConv, deleteConv } from "../chatws.js";

/* Pending delete — holds the conv id of the conversation the user asked to
   remove, so the confirm dialog can show inline instead of a native alert. */
const pendingDelete = ref(null);

function askDelete(e, convId) {
  e.stopPropagation();
  pendingDelete.value = convId;
}

function confirmDelete() {
  const id = pendingDelete.value;
  pendingDelete.value = null;
  if (id) {
    deleteConv(id);
    showToast("Conversation deleted");
  }
}

function cancelDelete() {
  pendingDelete.value = null;
}

/* "10:47 AM" for today, "Yesterday", then a short date — the same vocabulary
   the old mock rows used, now computed from the JSONL's mtime. */
function when(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const now = new Date();
  const startOfDay = t => new Date(t.getFullYear(), t.getMonth(), t.getDate());
  const days = Math.round((startOfDay(now) - startOfDay(d)) / 86400000);
  if (days <= 0) return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (days === 1) return "Yesterday";
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function close() { store.historyOpen = false; }

// Press Escape to close the history overlay
function onKey(e) {
  if (!store.historyOpen) return;
  if (e.key === "Escape") close();
}

// Click anywhere outside the history panel closes it
function onClickOutside(e) {
  if (!store.historyOpen) return;
  const panel = document.getElementById("chat-history");
  if (panel && !panel.contains(e.target)) close();
}

onMounted(() => {
  document.addEventListener("keydown", onKey);
  document.addEventListener("click", onClickOutside);
});
onUnmounted(() => {
  document.removeEventListener("keydown", onKey);
  document.removeEventListener("click", onClickOutside);
});
</script>

<template>
  <div id="chat-history">
    <div class="panel-header">
      <span>History</span>
      <button class="x-btn" @click="close()">✕</button>
    </div>
    <div v-for="c in store.chat.convs" :key="c.id" class="hist-row" @click="openConv(c.id)">
      <span class="hw">{{ when(c.updated) }}</span>
      <span class="ht">{{ c.title }}</span>
      <span class="del-slot">
        <button class="del-btn" data-tip="Delete" @click="askDelete($event, c.id)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
        </button>
      </span>
    </div>
    <div v-if="!store.chat.convs.length" class="hist-empty">
      No conversations yet — every chat lands here once you send a message.
    </div>

    <!-- Inline confirm dialog — same visual language as NewClientModal -->
    <div v-if="pendingDelete" id="confirm-overlay" @click="cancelDelete">
      <div id="confirm-box" @click.stop>
        <div class="cf-head"><span>Delete Conversation</span></div>
        <div class="cf-body">This cannot be undone. The conversation and all its messages will be permanently removed.</div>
        <div class="cf-foot">
          <button class="btn-sm" @click="cancelDelete">Cancel</button>
          <button class="btn-sm danger" @click="confirmDelete">Delete</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* History overlay covers the message area, flush against the header's
   bottom border. Must match #chat-header height: 11px padding × 2 + 15px
   icon height + 1px border = 38px. */
#chat-history {
  position: absolute; top: 38px; left: 0; right: 0; bottom: 0;
  background: var(--bg); z-index: 40; overflow-y: auto;
}
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  font: 700 10px var(--mono); letter-spacing: 2px; text-transform: uppercase;
  color: var(--text-3);
}
.x-btn {
  background: none; border: none; color: var(--text-4);
  font-size: 12px; cursor: pointer; padding: 0; line-height: 1;
}
.x-btn:hover { color: var(--red); }
.hist-row {
  padding: 10px 14px; cursor: pointer;
  border-bottom: 1px solid var(--bg-panel);
  display: flex; align-items: center; gap: 10px;
}
.hist-row:hover { background: var(--bg-hover); }
.hist-row .hw {
  font: 400 10px var(--mono); color: var(--text-4);
  flex-shrink: 0; width: 62px;
}
.hist-row .ht {
  font: 500 12px var(--sans); color: var(--text-2);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  flex: 1; min-width: 0;
}
.hist-row:hover .ht { color: var(--text); }
.del-slot {
  flex-shrink: 0; width: 16px;
  display: flex; align-items: center; justify-content: center;
}
.del-btn {
  background: none; border: none; color: var(--text-4);
  cursor: pointer; padding: 2px; line-height: 0;
  display: flex; opacity: 0; transition: opacity 0.15s, color 0.15s;
}
.del-btn svg { width: 13px; height: 13px; }
.hist-row:hover .del-btn { opacity: 1; }
.del-btn:hover { color: var(--red); }
.hist-empty { padding: 14px; font: 400 11px var(--mono); color: var(--text-4); }

/* Inline confirm — mirrors #modal-overlay / #modal from NewClientModal so the
   two dialogs read as the same component family. */
#confirm-overlay {
  position: fixed; inset: 0; background: var(--scrim); z-index: 200;
  display: flex; align-items: center; justify-content: center;
}
#confirm-box {
  width: 380px; background: var(--bg-panel); border: 1px solid var(--border-soft);
}
.cf-head {
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  font: 700 10px var(--mono); letter-spacing: 2px; text-transform: uppercase;
  color: var(--text-3);
}
.cf-body {
  padding: 16px; font: 400 12px var(--sans); color: var(--text-2); line-height: 1.6;
}
.cf-foot {
  padding: 12px 16px; border-top: 1px solid var(--border);
  display: flex; gap: 8px; justify-content: flex-end;
}
.btn-sm.danger {
  background: var(--red); border-color: var(--red); color: #fff; font-weight: 700;
}
.btn-sm.danger:hover { filter: brightness(1.1); color: #fff; }
</style>
