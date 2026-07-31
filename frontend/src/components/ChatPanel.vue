<script setup>
/* AI panel: structured message thread (ChatMessage.vue) fed by chatws.js,
   contenteditable composer with pill drops, custom model picker, history
   overlay. Send turns into Stop while a reply streams. */
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from "vue";
import { store, openModelSettings, showToast, scopeNow, setModel, modelLabel, TREE_MIME, CLIENT_MIME } from "../store.js";
import { newChat, sendMessage, cancelStream } from "../chatws.js";
import { insertPill } from "../utils.js";
import ChatHistory from "./ChatHistory.vue";
import ChatMessage from "./ChatMessage.vue";

const messagesEl = ref(null);
const inputEl = ref(null);
const dragover = ref(false);
const menuOpen = ref(false);

// System/tool rows are context plumbing, not conversation — don't render them.
// Assistant tool_calls rounds are plumbing too: their text is process notes,
// the real answer is the final assistant message without tool_calls.
const visible = computed(() =>
  store.chat.messages.filter(m => (m.role === "user" || m.role === "assistant")
    && !(m.tool_calls && m.tool_calls.length)));

// The gap between "sent" and the first token/tool event. chatws.js only
// pushes the _streaming placeholder when something arrives, so until then the
// thread looks dead — fill it with a typing indicator, WeChat-style.
const waiting = computed(() => {
  const m = store.chat.messages;
  const last = m[m.length - 1];
  return store.chat.streaming && !(last && last._streaming);
});

function scrollToBottom() {
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
}

/* Auto-follow only while the user is at the bottom. Scrolling up during a
   stream means "I'm reading" — fighting that scroll is worse than missing
   a token. Programmatic scrolls land exactly at the bottom, so the handler
   re-arms itself; wheeling back down re-enables following naturally. */
const stick = ref(true);
function onScroll() {
  const el = messagesEl.value;
  if (el) stick.value = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
}

// Follow both new messages and the growing tail of a streamed one
watch(() => {
  const m = store.chat.messages;
  const last = m[m.length - 1];
  return `${m.length}:${last && last.content ? last.content.length : 0}`;
}, async () => { if (!stick.value) return; await nextTick(); scrollToBottom(); });
// A different conversation always opens at its tail
watch(() => store.chat.convId, async () => {
  stick.value = true; await nextTick(); scrollToBottom();
});
onMounted(scrollToBottom);

/* --- Send: serialize the composer into text + pills for chatws.js.
   File pills ride as {scope,path} attachments; quote pills fold into the
   text as blockquotes (they're words, not files). --- */
function sendMsg() {
  if (store.chat.streaming) { cancelStream(); return; }
  const input = inputEl.value;
  const pills = [];
  let quotes = "", skipped = 0;
  input.querySelectorAll(".pill").forEach(p => {
    if (p.dataset.quote) {
      const from = p.dataset.path ? `\n> — ${p.dataset.scope}/${p.dataset.path}` : "";
      quotes += `\n\n> ${p.dataset.quote.replace(/\n/g, "\n> ")}${from}`;
    } else if (p.dataset.scope) {
      pills.push({ scope: p.dataset.scope, path: p.dataset.path });
    } else {
      skipped++;  // OS drop — no repo identity, the agent can't read it
    }
  });
  if (skipped) showToast("Drop OS files into the file tree first — only workspace files attach");
  const clone = input.cloneNode(true);
  clone.querySelectorAll(".pill").forEach(x => x.remove());
  const text = (clone.textContent.trim() + quotes).trim();
  if (!text && !pills.length) return;
  if (sendMessage(text, pills)) {
    input.innerHTML = "";
    stick.value = true;   // your own message always snaps the view down
  }
}

function onKey(e) {
  // Enter sends; Shift+Enter inserts a newline
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMsg();
  }
}

/* Paste as plain text. The default contenteditable paste keeps clipboard
   HTML — fonts, colors, whole table markup from PDFs and web pages — which
   pollutes the composer and rides into the prompt. execCommand keeps the
   caret position and the undo stack, which manual Range surgery loses. */
function onPaste(e) {
  e.preventDefault();
  const text = e.clipboardData.getData("text/plain");
  if (text) document.execCommand("insertText", false, text);
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
    // A client row dragged off the list: one folder pill for the whole client
    // — {scope: id, path: ""} is the same address the backend already speaks.
    const c = e.dataTransfer.getData(CLIENT_MIME);
    if (c) {
      try {
        const { id, name } = JSON.parse(c);
        if (id) insertPill(name || id, true, { scope: id, path: "" });
      } catch { /* malformed drag payload — ignore */ }
      return;
    }
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
      <span class="title"><span>{{ store.chat.title }}</span>
        <span v-if="!store.chat.online" class="offline" data-tip="Agent service offline">●</span>
      </span>
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
    <div id="messages" ref="messagesEl" @scroll="onScroll">
      <ChatMessage v-for="(m, i) in visible" :key="i" :msg="m" />
      <div v-if="waiting" class="typing"><span></span><span></span><span></span></div>
      <div v-if="!visible.length" class="empty-thread">
        New chat · ask about a client, or drop a file.
      </div>
    </div>
    <div id="composer">
      <div id="input-wrap" :class="{ dragover }"
           @dragenter.prevent="dragover = true" @dragover.prevent="dragover = true"
           @dragleave="dragover = false" @drop.prevent="onDrop">
        <div id="chat-input" ref="inputEl" contenteditable="true"
             data-placeholder="Ask about this client, or drop a file…" @keydown="onKey" @paste="onPaste"></div>
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
          <button id="send-btn" :class="{ stop: store.chat.streaming }"
                  :data-tip="store.chat.streaming ? 'Stop' : undefined"
                  @click="sendMsg()">{{ store.chat.streaming ? "■" : "↑" }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
#chat {
  /* No max-width: reading a wide table sometimes needs most of the window.
     The divider clamp (App.vue) keeps the center area usable instead. */
  width: 380px; min-width: 300px;
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
  min-width: 0;
}
#chat-header .title > span:first-child {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* Agent WS down — a quiet dot, not a modal; chatws.js keeps retrying */
#chat-header .offline { color: var(--red); flex-shrink: 0; }
.ch-icons { display: flex; gap: 12px; color: var(--text-4); }
.ch-icons span { cursor: pointer; display: flex; }
.ch-icons svg { width: 15px; height: 15px; }
.ch-icons span:hover { color: var(--brand); }
#messages { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 16px; }
.empty-thread { color: var(--text-4); font: 400 11.5px var(--mono); padding: 6px 2px; }
/* Waiting-for-first-token dots — assistant side, quiet, no bubble chrome */
.typing { display: flex; gap: 4px; padding: 4px 2px; }
.typing span {
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--text-4);
  animation: typing-blink 1.2s infinite ease-in-out;
}
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing-blink {
  0%, 60%, 100% { opacity: 0.25; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-3px); }
}
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
  margin-left: auto; width: 23px; height: 23px;
  background: var(--brand); border: none; color: var(--on-brand); cursor: pointer; font: 700 12px var(--mono);
}
#send-btn:hover { filter: brightness(1.15); }
/* Stop stays brand green — same button, different glyph; red reads as error */
#send-btn.stop { font-size: 9px; }
</style>
