<script setup>
/* AI panel: structured message thread (ChatMessage.vue) fed by chatws.js,
   contenteditable composer with pill drops, custom model picker, history
   overlay. Send turns into Stop while a reply streams. */
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from "vue";
import { store, openModelSettings, openConvTabCtx, showToast, scopeNow, setModel, modelLabel, TREE_MIME, CLIENT_MIME, uploadForChat } from "../store.js";
import { newChatTab, closeConvTab, sendMessage, cancelStream } from "../chatws.js";
import { insertPill, insertQuotePill } from "../utils.js";
import ChatHistory from "./ChatHistory.vue";
import ChatMessage from "./ChatMessage.vue";

const messagesEl = ref(null);
const inputEl = ref(null);
const dragover = ref(false);
const menuOpen = ref(false);

// The tab strip drives everything below it — thread, composer guards and the
// send/stop button all read the focused conversation's bucket.
const activeCs = computed(() =>
  store.chat.active ? (store.chat.byConv[store.chat.active] || null) : null);

// System/tool rows are context plumbing, not conversation — don't render them.
// Assistant tool_calls rounds are plumbing too: their text is process notes,
// the real answer is the final assistant message without tool_calls.
const visible = computed(() =>
  (activeCs.value ? activeCs.value.messages : []).filter(m => (m.role === "user" || m.role === "assistant")
    && !(m.tool_calls && m.tool_calls.length)));

// The index of the last real user message (skipping _recalled placeholders)
// so ChatMessage knows when to show the "Recall" button.
const lastUserIdx = computed(() => {
  const v = visible.value;
  for (let i = v.length - 1; i >= 0; i--) {
    if (v[i].role === "user" && !v[i]._recalled) return i;
  }
  return -1;
});

// The gap between "sent" and the first token/tool event. chatws.js only
// pushes the _streaming placeholder when something arrives, so until then the
// thread looks dead — fill it with a typing indicator, WeChat-style.
const waiting = computed(() => {
  const cs = activeCs.value;
  if (!cs) return false;
  const last = cs.messages[cs.messages.length - 1];
  return cs.streaming && !(last && last._streaming);
});

function scrollToBottom() {
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
}

/* Tab strip: clicking focuses (chatws keeps the tab list authoritative);
   the little × closes without deleting the conversation itself. */
function focusTab(id) { store.chat.active = id; }

/* Composer resize: drag the grip up to grow the input, capped so the thread
   always keeps room. 0 means auto — the box grows with its content instead. */
const INPUT_MIN_H = 68, INPUT_MAX_H = 320;
const inputH = ref(0);
function startResize(e) {
  e.preventDefault();
  const startY = e.clientY;
  const startH = inputEl.value ? inputEl.value.offsetHeight : INPUT_MIN_H;
  const move = ev => {
    inputH.value = Math.max(INPUT_MIN_H, Math.min(INPUT_MAX_H, startH + (startY - ev.clientY)));
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
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
  const cs = activeCs.value;
  const m = cs ? cs.messages : [];
  const last = m[m.length - 1];
  return `${store.chat.active}:${m.length}:${last && last.content ? last.content.length : 0}`;
}, async () => { if (!stick.value) return; await nextTick(); scrollToBottom(); });
// A different tab always opens at its tail
watch(() => store.chat.active, async () => {
  stick.value = true; await nextTick(); scrollToBottom();
});
onMounted(scrollToBottom);

/* --- Send: serialize the composer into text + pills for chatws.js.
   File pills ride as {scope,path,name,dir}; quotes stay structured too —
   the server folds both into the model's prompt, while the thread renders
   them back as components (ChatMessage chips), never as serialized text. --- */
function sendMsg() {
  let convId = store.chat.active;
  // Typing into an empty panel opens a fresh tab on demand — chat no longer
  // auto-creates a conversation at boot.
  if (!convId) { newChatTab(); convId = store.chat.active; if (!convId) return; }
  const cs = store.chat.byConv[convId];
  if (cs && cs.streaming) { cancelStream(convId); return; }
  const input = inputEl.value;
  const pills = [], quotes = [];
  let skipped = 0;
  input.querySelectorAll(".pill").forEach(p => {
    if (p.dataset.quote) {
      quotes.push({ text: p.dataset.quote, scope: p.dataset.scope || "",
                    path: p.dataset.path || "" });
    } else if (p.dataset.scope) {
      pills.push({ scope: p.dataset.scope, path: p.dataset.path,
                   name: p.dataset.name || String(p.dataset.path || "").split("/").pop() || p.dataset.scope,
                   dir: !!p.dataset.dir });
    } else {
      skipped++;  // OS drop — no repo identity, the agent can't read it
    }
  });
  if (skipped) showToast("Drop OS files into the file tree first — only workspace files attach");
  const clone = input.cloneNode(true);
  clone.querySelectorAll(".pill").forEach(x => x.remove());
  const text = clone.textContent.trim();
  if (!text && !pills.length && !quotes.length) return;
  if (sendMessage(convId, text, pills, quotes)) {
    input.innerHTML = "";
    stick.value = true;   // your own message always snaps the view down
  }
}

/* Re-edit a recalled message: put the original text back into the
   composer and restore any attached file/quote pills. The placeholder
   stays in the thread (just like WeChat). */
function onReEdit({ text, pills, quotes }) {
  // Restore text into the composer
  const input = inputEl.value;
  input.innerHTML = "";
  if (text) input.textContent = text;

  // Restore file/folder pills
  for (const p of (pills || [])) {
    insertPill(p.name || "", !!p.dir, { scope: p.scope, path: p.path });
  }

  // Restore quote pills
  for (const q of (quotes || [])) {
    insertQuotePill(q.text || "", { scope: q.scope, path: q.path });
  }

  input.focus();
  // Place the cursor at the end so the user can keep typing
  const sel = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(input);
  range.collapse(false);
  sel.removeAllRanges();
  sel.addRange(range);
  stick.value = true;
}

function onKey(e) {
  // The mention menu owns its keys first: arrows move the highlight, Enter /
  // Tab commit, Esc backs out — none of them may fall through to send.
  if (mentionOpen.value) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      mentionIdx.value = mentionIdx.value >= mentionList.value.length - 1 ? 0 : mentionIdx.value + 1;
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      mentionIdx.value = mentionIdx.value <= 0 ? mentionList.value.length - 1 : mentionIdx.value - 1;
      return;
    }
    if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      if (mentionList.value[mentionIdx.value]) pickMention(mentionList.value[mentionIdx.value]);
      else closeMention();
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      closeMention();
      return;
    }
  }
  // Enter sends; Shift+Enter inserts a newline
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMsg();
  }
}

/* --- @ mention: typing @ opens the client picker above the composer.
   Committing a client is exactly the drag-off-the-list gesture — one folder
   pill {scope: clientId, path: ""} — but discoverable without knowing the
   sidebar drag exists. Clicking into a client already makes it the implicit
   context; this makes context attachment explicit instead. --- */
const mentionQuery = ref("");
const mentionAnchor = ref(null);   // {node, offset} — where the @ sits
const mentionIdx = ref(0);
// Open clients first, archived after — same order the list shows them
const mentionList = computed(() => {
  const q = mentionQuery.value.trim().toLowerCase();
  const all = store.clients.concat(store.closed);
  const hits = q ? all.filter(c => (c.name || "").toLowerCase().includes(q)) : all;
  return hits.slice(0, 8);
});
const mentionOpen = computed(() => mentionAnchor.value !== null);

// Walk back from the caret through the current text run: a live mention is
// an @ preceded by line-start or whitespace, with no whitespace after it yet.
function scanMention() {
  const input = inputEl.value;
  const sel = window.getSelection();
  if (!input || !sel.rangeCount) { closeMention(); return; }
  const range = sel.getRangeAt(0);
  if (!range.collapsed || range.startContainer.nodeType !== Node.TEXT_NODE
      || !input.contains(range.startContainer)) { closeMention(); return; }
  const text = range.startContainer.textContent.slice(0, range.startOffset);
  const m = /(^|[\s\u00A0])@([^\s\u00A0]*)$/.exec(text);
  if (!m) { closeMention(); return; }
  mentionAnchor.value = { node: range.startContainer, at: range.startOffset - m[2].length - 1 };
  mentionQuery.value = m[2];
  mentionIdx.value = 0;
}

function closeMention() { mentionAnchor.value = null; mentionQuery.value = ""; }

function pickMention(c) {
  const a = mentionAnchor.value;
  const q = mentionQuery.value;  // capture before closeMention wipes it
  closeMention();
  if (!a || !c || !c.id) return;
  const input = inputEl.value;
  input.focus();
  // Erase the @query the user typed, then drop the pill where it stood —
  // placePillAtCaret reads the selection we leave behind.
  try {
    const sel = window.getSelection();
    const r = document.createRange();
    r.setStart(a.node, a.at);
    r.setEnd(a.node, Math.min(a.node.textContent.length, a.at + 1 + q.length));
    r.deleteContents();
    sel.removeAllRanges();
    sel.addRange(r);
  } catch { return; }  // text node mutated mid-flight — bail cleanly
  insertPill(c.name || c.id, true, { scope: c.id, path: "" });
}

// The menu rows preventDefault on mousedown so picking never blurs the
// composer; a genuine blur (clicking anywhere else) dismisses the menu.
function onInputBlur(e) {
  if (mentionOpen.value && e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest("#mention-menu")) return;
  closeMention();
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

/* --- Drops from Finder (real files) and the file tree (text payload).
   The whole panel is the target, not just the input box — hitting a 34px
   strip at the end of a cross-window drag is precision work nobody asked
   for. Wherever the drop lands, the pill goes into the composer. --- */
function onDrop(e) {
  dragover.value = false;
  // Insert at wherever the caret already is — not wherever the mouse happens
  // to be at the exact pixel it was released. caretRangeFromPoint used to
  // re-target selection to the drop coordinates, which felt unstable: a
  // cross-window drag rarely lands the pointer on the exact character you
  // meant, so the pill would appear in a seemingly random spot. Leaving
  // selection untouched keeps it at the caret from your last click/typing;
  // placePillAtCaret's own fallback appends at the end if that caret isn't
  // inside the input at all (e.g. it was never focused this session).
  if (e.dataTransfer.types.includes("Files")) {
    // OS file/folder drop — upload into the current repo first so the agent gets
    // a real path it can read. Folder drops become one folder pill, not dozens
    // of file pills; mixed drops create one pill per top-level item.
    uploadForChat(e).then(uploaded => {
      uploaded.forEach(p => insertPill(p.name, !!p.dir, { scope: p.scope, path: p.path }));
      inputEl.value?.focus();
    });
    return;
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
    // Tree drags carry a plain path string; tab drags carry {scope, path} JSON;
    // a multi-selection tree drag carries {paths:[{path,name,dir},…]} — one pill
    // per node, exactly what right-click "Add to Chat" produces.
    const p = e.dataTransfer.getData(TREE_MIME);
    if (p) {
      let parsed = null;
      try { parsed = JSON.parse(p); } catch { /* plain single path */ }
      if (parsed && Array.isArray(parsed.paths)) {
        for (const s of parsed.paths)
          insertPill(s.name || String(s.path || "").split("/").pop(), !!s.dir,
                      { scope: scopeNow(), path: s.path });
        inputEl.value?.focus();
        return;
      }
      const fileAddr = parsed || { scope: scopeNow(), path: p };
      if (t) insertPill(t.replace(/\/$/, ""), t.endsWith("/"), fileAddr);
      return;
    }
    if (t) insertPill(t.replace(/\/$/, ""), t.endsWith("/"), null);
  }
}

/* dragleave fires on every child hop; only leaving the panel itself counts.
   relatedTarget is null when the drag exits the window — that counts too. */
function onDragLeave(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) dragover.value = false;
}

/* --- Model picker: whatever settings.yaml configured, nothing more --- */
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
  <div id="chat" :class="{ dragover }"
       @dragenter.prevent="dragover = true" @dragover.prevent="dragover = true"
       @dragleave="onDragLeave" @drop.prevent="onDrop">
    <div id="chat-header">
      <!-- Tab strip shares the header row with the + / history icons; the
           tab itself carries the title, so no duplicate heading above. -->
      <div id="conv-tabs" v-if="store.chat.open.length">
        <div v-for="id in store.chat.open" :key="id" class="conv-tab"
             :class="{ active: id === store.chat.active, streaming: (store.chat.byConv[id] || {}).streaming }"
             @click="focusTab(id)" @contextmenu.prevent="openConvTabCtx($event, id)">
          <span class="ct-dot"></span>
          <span class="ct-title">{{ (store.chat.byConv[id] || {}).title || "New Chat" }}</span>
          <span class="ct-x" data-tip="Close tab" @click.stop="closeConvTab(id)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
          </span>
        </div>
      </div>
      <span class="ch-icons">
        <span v-if="!store.chat.online" class="offline" data-tip="Agent service offline">●</span>
        <span data-tip="New chat" @click="newChatTab()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>
        </span>
        <span data-tip="Chat history" @click.stop="store.historyOpen = !store.historyOpen">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>
        </span>
      </span>
    </div>
    <ChatHistory v-show="store.historyOpen" />
    <div id="messages" ref="messagesEl" @scroll="onScroll">
      <ChatMessage v-for="(m, i) in visible" :key="i" :msg="m" :convId="store.chat.active" :isLastUser="i === lastUserIdx" @reedit="onReEdit" />
      <div v-if="waiting" class="typing"><span></span><span></span><span></span></div>
      <div v-if="!visible.length" class="empty-thread">
        New chat · ask a question, or drop a file.
      </div>
    </div>
    <div id="composer">
      <!-- Invisible drag strip: the ns-resize cursor is the only affordance;
           double-click snaps the height back to auto -->
      <div id="resize-grip" @pointerdown="startResize" @dblclick="inputH = 0"></div>
      <div id="input-wrap" :class="{ dragover }">
        <div id="chat-input" ref="inputEl" contenteditable="true"
             :style="inputH ? { height: inputH + 'px' } : null"
             data-placeholder="Ask a question, drop a file, or @ a client…"
             @keydown="onKey" @input="scanMention" @paste="onPaste" @blur="onInputBlur"></div>
        <!-- @ client picker — anchored above the box like the model menu -->
        <div id="mention-menu" v-if="mentionOpen">
          <div v-for="(c, i) in mentionList" :key="c.id" class="mn-item" :class="{ sel: i === mentionIdx }"
               @mousedown.prevent="pickMention(c)" @mouseenter="mentionIdx = i">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="7.5" r="4"/><path d="M4.5 21c.6-4 3.6-6.5 7.5-6.5s6.9 2.5 7.5 6.5"/></svg>
            <span class="mn-name">{{ c.name }}</span>
            <span class="mn-meta">{{ c.purpose }} · {{ c.amount }}</span>
          </div>
          <div v-if="!mentionList.length" class="mn-item none">no client matches</div>
        </div>
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
          <button id="send-btn" :class="{ stop: activeCs && activeCs.streaming }"
                  :data-tip="activeCs && activeCs.streaming ? 'Stop' : undefined"
                  @click="sendMsg()">{{ activeCs && activeCs.streaming ? "■" : "↑" }}</button>
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
/* The whole panel accepts drops — say so at the panel edge too */
#chat.dragover { border-left-color: var(--brand); }
#chat-header {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 10px 6px 6px;
  border-bottom: 1px solid var(--border); flex-shrink: 0; user-select: none;
}
/* Agent WS down — a quiet dot, not a modal; chatws.js keeps retrying */
#chat-header .offline { color: var(--red); flex-shrink: 0; font-size: 10px; }
.ch-icons { display: flex; gap: 12px; color: var(--text-4); margin-left: auto; flex-shrink: 0; align-items: center; }
.ch-icons span { cursor: pointer; display: flex; }
.ch-icons svg { width: 15px; height: 15px; }
.ch-icons span:hover { color: var(--brand); }
/* The offline dot is a status, not a button — no pointer, no hover tint */
.ch-icons .offline, .ch-icons .offline:hover { cursor: default; color: var(--red); }
/* Conversation tab strip — shares the header row with the + / history icons;
   several clients stream in parallel, one tab each, focused one highlighted. */
#conv-tabs {
  display: flex; gap: 2px; overflow-x: auto; flex: 1; min-width: 0;
  user-select: none; scrollbar-width: thin;
}
.conv-tab {
  display: flex; align-items: center; gap: 6px;
  max-width: 150px; padding: 4px 8px; cursor: pointer; flex-shrink: 0;
  border: 1px solid transparent;
  font: 400 10.5px var(--mono); color: var(--text-3); white-space: nowrap;
}
.conv-tab:hover { color: var(--text-2); background: var(--bg-hover); }
.conv-tab.active { color: var(--text); background: var(--bg-hover); border-color: var(--border); }
.ct-title { overflow: hidden; text-overflow: ellipsis; }
/* Streaming tab: a quiet pulse dot says "still answering" even unfocused */
.ct-dot { width: 5px; height: 5px; border-radius: 50%; background: transparent; flex-shrink: 0; }
.conv-tab.streaming .ct-dot { background: var(--brand); animation: typing-blink 1.2s infinite ease-in-out; }
/* The × appears on hover/active so a busy strip stays readable */
.ct-x { display: flex; opacity: 0; flex-shrink: 0; color: var(--text-4); }
.ct-x:hover { color: var(--red); }
.conv-tab:hover .ct-x, .conv-tab.active .ct-x { opacity: 1; }
.ct-x svg { width: 9px; height: 9px; }
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
/* Empty settings.yaml — a label, not a choice */
.m-item.none { color: var(--text-4); cursor: default; }
.m-item.none:hover { background: none; color: var(--text-4); }
.m-sep { height: 1px; background: var(--border); margin: 4px 0; }
#composer { border-top: 1px solid var(--border); flex-shrink: 0; }
/* Invisible drag strip — cursor change alone says "resizable" */
#resize-grip { height: 10px; cursor: ns-resize; user-select: none; background: var(--bg-hover); }
/* Full-bleed composer — no outer padding, the input owns the whole strip.
   No focus chrome: the caret is enough; only a file drag tints the strip. */
#input-wrap { background: var(--bg-hover); padding: 9px 12px; position: relative; }
#input-wrap.dragover { background: var(--tint-green); box-shadow: inset 0 1px 0 var(--brand); }
#chat-input {
  width: 100%; min-height: 68px; max-height: 320px; overflow-y: auto;
  background: transparent; border: none; outline: none;
  color: var(--text); font: 400 12px var(--mono); line-height: 1.9;
}
/* Placeholder for the contenteditable composer */
#chat-input:empty::before { content: attr(data-placeholder); color: var(--text-4); pointer-events: none; }
/* @ client picker — same anchored-menu shape as the model picker */
#mention-menu {
  position: absolute; bottom: calc(100% + 6px); left: -1px; right: -1px;
  background: var(--bg-panel); border: 1px solid var(--border-soft); z-index: 50;
  max-height: 240px; overflow-y: auto;
}
.mn-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 12px; font: 400 11px var(--mono); color: var(--text-2); cursor: pointer;
}
.mn-item svg { width: 13px; height: 13px; color: var(--text-4); flex-shrink: 0; }
.mn-item.sel { background: var(--bg-raise); color: var(--text); }
.mn-item.sel svg { color: var(--brand); }
.mn-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mn-meta { margin-left: auto; color: var(--text-4); font-size: 10px; white-space: nowrap; }
.mn-item.none { color: var(--text-4); cursor: default; }
.mn-item.none:hover { background: none; }
#input-actions { display: flex; align-items: center; margin-top: 6px; }
#send-btn {
  margin-left: auto; width: 23px; height: 23px;
  background: var(--brand); border: none; color: var(--on-brand); cursor: pointer; font: 700 12px var(--mono);
}
#send-btn:hover { filter: brightness(1.15); }
/* Stop stays brand green — same button, different glyph; red reads as error */
#send-btn.stop { font-size: 9px; }
</style>
