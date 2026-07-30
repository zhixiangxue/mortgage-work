<script setup>
/* AI panel: v-html thread + DOM-decorated message actions, contenteditable
   composer with pill drops, custom model picker, history overlay. */
import { ref, watch, nextTick, onMounted, onUnmounted } from "vue";
import { store, openModelSettings, newChat, showToast, scopeNow, setModel, modelLabel, TREE_MIME } from "../store.js";
import { insertPill } from "../utils.js";
import ChatHistory from "./ChatHistory.vue";

const messagesEl = ref(null);
const inputEl = ref(null);
const dragover = ref(false);
const menuOpen = ref(false);

/* --- Message decoration: AI turns get copy + delete; user turns delete only.
   Runs over the v-html output, so buttons use window globals (bridge.js). --- */
const SVG_COPY = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
const SVG_TRASH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>`;

function decorateMessages() {
  if (!messagesEl.value) return;
  messagesEl.value.querySelectorAll(".msg").forEach(m => {
    if (m.querySelector(".msg-acts")) return;
    const isAI = m.classList.contains("ai");
    const acts = document.createElement("div");
    acts.className = "msg-acts";
    acts.innerHTML =
      (isAI ? `<button data-tip="Copy" onclick="copyMsg(this)">${SVG_COPY}</button>` : "") +
      `<button class="del" data-tip="Delete" onclick="delMsg(this)">${SVG_TRASH}</button>`;
    m.appendChild(acts);
  });
}

function scrollToBottom() {
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
}

watch(() => store.chatHtml, async () => {
  await nextTick();
  decorateMessages();
  scrollToBottom();
});
onMounted(() => { decorateMessages(); scrollToBottom(); });

/* --- Send loop: user turn + canned AI reply, appended straight to the DOM
   (v-html only re-renders on thread switch, same as the old innerHTML swap) --- */
function sendMsg() {
  const input = inputEl.value;
  const clone = input.cloneNode(true);
  clone.querySelectorAll(".pill .x").forEach(x => x.remove());
  const html = clone.innerHTML.trim();
  const text = clone.textContent.trim();
  const n = clone.querySelectorAll(".pill").length;
  if (!text && !n) return;
  const msgs = messagesEl.value;
  msgs.insertAdjacentHTML("beforeend",
    `<div class="msg user"><div class="bubble">${html}</div></div>`);
  input.innerHTML = "";
  decorateMessages();
  scrollToBottom();
  // Canned reply so the send loop feels alive in the demo
  setTimeout(() => {
    msgs.insertAdjacentHTML("beforeend",
      `<div class="msg ai"><div class="bubble">On it — ${n ? `reading ${n} attached item${n > 1 ? "s" : ""}… ` : ""}<span class="dim">(demo reply · ${modelLabel(store.currentModel) || "no model configured"})</span></div></div>`);
    decorateMessages();
    scrollToBottom();
  }, 700);
}

function onKey(e) {
  // Enter sends; Shift+Enter inserts a newline
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMsg();
  }
}

/* --- Drops from Finder (real files) and the file tree (text payload) --- */
function onDrop(e) {
  dragover.value = false;
  // Drop at the pointer position inside the text, like a rich-text editor
  const r = document.caretRangeFromPoint(e.clientX, e.clientY);
  if (r && inputEl.value.contains(r.startContainer)) {
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(r);
  }
  if (e.dataTransfer.files.length) {
    [...e.dataTransfer.files].forEach(f => insertPill(f.name, false));
  } else {
    const t = e.dataTransfer.getData("text/plain");
    // Tree drags also carry their tree-relative path — pin the file's real
    // identity to the pill instead of just a basename
    const p = e.dataTransfer.getData(TREE_MIME);
    if (t) insertPill(t.replace(/\/$/, ""), t.endsWith("/"),
                      p ? { scope: scopeNow(), path: p } : null);
  }
}

/* --- Model picker: whatever models.yaml configured, nothing more --- */
function pickModel(m) {
  setModel(m.ref);
  menuOpen.value = false;
}

function openSettings() {
  menuOpen.value = false;
  // Model config is just another file tab — consistent with everything-is-a-file
  openModelSettings();
}

const closeMenu = () => { menuOpen.value = false; };
onMounted(() => document.addEventListener("click", closeMenu));
onUnmounted(() => document.removeEventListener("click", closeMenu));
</script>

<template>
  <div id="chat">
    <div id="chat-header">
      <span class="title"><span>{{ store.chatTitle }}</span></span>
      <span class="ch-icons">
        <span data-tip="New chat" @click="newChat()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>
        </span>
        <span data-tip="Chat history" @click="store.historyOpen = !store.historyOpen">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>
        </span>
      </span>
    </div>
    <ChatHistory v-show="store.historyOpen" />
    <div id="messages" ref="messagesEl" v-html="store.chatHtml"></div>
    <div id="composer">
      <div id="input-wrap" :class="{ dragover }"
           @dragenter.prevent="dragover = true" @dragover.prevent="dragover = true"
           @dragleave="dragover = false" @drop.prevent="onDrop">
        <div id="chat-input" ref="inputEl" contenteditable="true"
             data-placeholder="Ask about this client, or drop a file…" @keydown="onKey"></div>
        <div id="input-actions">
          <div id="model-wrap">
            <button id="model-btn" @click.stop="menuOpen = !menuOpen">
              {{ modelLabel(store.currentModel) || "no model" }} <span style="font-size:8px;color:var(--text-4)">▾</span>
            </button>
            <div id="model-menu" v-show="menuOpen">
              <div v-for="m in store.models" :key="m.ref" class="m-item" @click="pickModel(m)">
                {{ m.label }}<span v-if="m.ref === store.currentModel" class="tick">✓</span>
              </div>
              <div v-if="!store.models.length" class="m-item none">nothing configured yet</div>
              <div class="m-sep"></div>
              <div class="m-item add" @click="openSettings()">Manage models…</div>
            </div>
          </div>
          <button id="send-btn" @click="sendMsg()">↑</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
#chat {
  width: 380px; min-width: 300px; max-width: 580px;
  background: var(--bg); border-left: 1px solid var(--border);
  display: flex; flex-direction: column; flex-shrink: 0;
  position: relative;
}
#chat-header {
  padding: 11px 14px;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid var(--border); flex-shrink: 0; user-select: none;
}
#chat-header .title {
  font: 700 10px var(--mono); letter-spacing: 2px; text-transform: uppercase;
  display: flex; align-items: center; gap: 8px;
}
.ch-icons { display: flex; gap: 12px; color: var(--text-4); }
.ch-icons span { cursor: pointer; display: flex; }
.ch-icons svg { width: 15px; height: 15px; }
.ch-icons span:hover { color: var(--brand); }
#messages { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 16px; }
/* Custom model picker — native <select> popups can't match the theme */
#model-wrap { position: relative; }
#model-btn {
  display: flex; align-items: center; gap: 6px;
  background: var(--bg-hover); border: 1px solid var(--border);
  color: var(--text-3); font: 400 10.5px var(--mono);
  padding: 4px 9px; cursor: pointer;
}
#model-btn:hover { border-color: var(--border-soft); color: var(--text-2); }
#model-menu {
  position: absolute; bottom: calc(100% + 6px); left: 0;
  min-width: 180px; background: var(--bg-panel);
  border: 1px solid var(--border-soft); z-index: 50;
}
.m-item {
  padding: 7px 12px; font: 400 11px var(--mono); color: var(--text-2);
  cursor: pointer; display: flex; justify-content: space-between; gap: 12px;
}
.m-item:hover { background: var(--bg-raise); color: var(--text); }
.m-item .tick { color: var(--brand); }
.m-item.add { color: var(--text-3); }
.m-item.add:hover { color: var(--brand); }
/* Empty models.yaml — a label, not a choice */
.m-item.none { color: var(--text-4); cursor: default; }
.m-item.none:hover { background: none; color: var(--text-4); }
.m-sep { height: 1px; background: var(--border); margin: 4px 0; }
#composer { padding: 12px 14px 14px; border-top: 1px solid var(--border); flex-shrink: 0; }
#input-wrap { background: var(--bg-hover); border: 1px solid var(--border); padding: 9px 10px; }
#input-wrap:focus-within { border-color: var(--brand); }
#input-wrap.dragover { border-color: var(--brand); background: var(--tint-green); }
#chat-input {
  width: 100%; min-height: 34px; max-height: 120px; overflow-y: auto;
  background: transparent; border: none; outline: none;
  color: var(--text); font: 400 12px var(--mono); line-height: 1.9;
}
/* Placeholder for the contenteditable composer */
#chat-input:empty::before { content: attr(data-placeholder); color: var(--text-4); pointer-events: none; }
#input-actions { display: flex; align-items: center; margin-top: 6px; }
#send-btn {
  margin-left: auto; width: 26px; height: 26px;
  background: var(--brand); border: none; color: var(--on-brand); cursor: pointer; font: 700 13px var(--mono);
}
#send-btn:hover { filter: brightness(1.15); }
</style>
