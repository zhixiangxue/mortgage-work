/* Chat over the agent WebSocket (agent_service.py).
   Owns the socket, the reconnect loop and the protocol mapping onto
   store.chat; components call the action functions below and render state.
   The store stays import-free of this module (chatws → store only), so there
   is no import cycle.

   Wire protocol (see agent_service.py docstring): new/open/list/send/cancel
   out; conv, convs, chunk, tool events, done, cancelled, error in — all keyed
   by conv_id, chak's own conversation id. */
import { store, showToast, focusChat, modelLabel } from "./store.js";

// Matches config.py's AGENT_PORT default; app.py injects the real URL as
// window.__SERVICES__.agent (resolved per attempt — injection can land late).
const DEFAULT_URL = "ws://127.0.0.1:8791/ws";

let ws = null;
let retries = 0;
let retryTimer = null;

function agentUrl() {
  return (window.__SERVICES__ && window.__SERVICES__.agent) || DEFAULT_URL;
}

export function initChatWS() {
  connect();
}

function connect() {
  clearTimeout(retryTimer);
  try { ws = new WebSocket(agentUrl()); } catch { scheduleRetry(); return; }
  ws.onopen = () => {
    retries = 0;
    store.chat.online = true;
    send({ type: "list" });
    // Session start opens a fresh conversation on whatever is focused; a
    // reconnect keeps the one already on screen, and a pending session
    // restore holds the "new" back — the convs handler decides instead.
    if (!store.chat.convId && !restoreConvId) send({ type: "new", context: currentContext() });
  };
  ws.onmessage = (e) => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    handle(msg);
  };
  ws.onclose = () => {
    ws = null;
    store.chat.online = false;
    // A drop mid-stream is a failed send: freeze the partial answer and flag
    // the question WeChat-style (retryable) instead of failing silently.
    if (store.chat.streaming) {
      const live = streamingMsg();
      if (live && !live.content && !(live.tools || []).length) store.chat.messages.pop();
      else if (live) delete live._streaming;
      markPendingFailed();
    }
    store.chat.streaming = false;
    scheduleRetry();
  };
  ws.onerror = () => { if (ws) try { ws.close(); } catch { /* already dead */ } };
}

function scheduleRetry() {
  // 1s → 2s → 4s → 8s → 10s cap. Quiet: in a plain browser without the agent
  // running this loop spins forever and must not toast.
  const delay = Math.min(10000, 1000 * 2 ** Math.min(retries++, 4));
  retryTimer = setTimeout(connect, delay);
}

function send(obj) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  ws.send(JSON.stringify(obj));
  return true;
}

/* What the conversation is about, captured at creation time (the server
   bakes it into the system prompt and the title). */
function currentContext() {
  const ctx = { view: store.view };
  if (store.view !== "products" && store.client)
    ctx.client = { id: store.client.id, name: store.client.name };
  return ctx;
}

/* ---- Incoming protocol → store.chat ---- */

function streamingMsg() {
  const m = store.chat.messages;
  const last = m[m.length - 1];
  return last && last._streaming ? last : null;
}

/* The optimistic user message of the in-flight turn (no turn_id yet — the
   backfill on done/cancelled is what clears it). Flagged messages render a
   red "!" that resends. */
function markPendingFailed() {
  const u = [...store.chat.messages].reverse()
    .find(m => m.role === "user" && !m.turn_id && !m._failed);
  if (u) u._failed = true;
}

function handle(msg) {
  const chat = store.chat;
  switch (msg.type) {
    case "conv":
      chat.convId = msg.meta.id;
      chat.title = msg.meta.title || "New Chat";
      chat.context = msg.meta.context || {};
      chat.messages = msg.messages || [];
      chat.streaming = false;
      store.historyOpen = false;
      break;
    case "convs":
      chat.convs = msg.items || [];
      // A session restore waits here: only ids the server actually lists are
      // reopened (the saved conv may have been deleted, or was a never-sent
      // New Chat that left no file). Otherwise fall back to a fresh one.
      if (restoreConvId) {
        const id = restoreConvId;
        restoreConvId = null;
        if (chat.convs.some(c => c.id === id) && chat.convId !== id)
          send({ type: "open", conv_id: id });
        else if (!chat.convId)
          send({ type: "new", context: currentContext() });
      }
      break;
    case "chunk": {
      if (msg.conv_id !== chat.convId) break;
      const live = streamingMsg();
      if (live) live.content += msg.content;
      else chat.messages.push({ role: "assistant", content: msg.content, _streaming: true });
      break;
    }
    // tools=[] in V1 so these never arrive; the mapping is here so the first
    // real tool lights up the trace block with no protocol work.
    case "tool_start": {
      const live = streamingMsg()
        || (chat.messages.push({ role: "assistant", content: "", _streaming: true }),
            chat.messages[chat.messages.length - 1]);
      (live.tools = live.tools || []).push(
        { call_id: msg.call_id, tool: msg.tool, status: "run" });
      break;
    }
    case "tool_end":
    case "tool_error": {
      const live = streamingMsg();
      const t = live && (live.tools || []).find(x => x.call_id === msg.call_id);
      if (t) { t.status = msg.type === "tool_end" ? "ok" : "error"; t.error = msg.error; }
      break;
    }
    case "done":
    case "cancelled": {
      if (msg.conv_id !== chat.convId) { send({ type: "list" }); break; }
      const live = streamingMsg();
      // The final dump replaces the accumulated chunks (same text + metadata);
      // keep the tool trace the placeholder collected.
      const finalMsg = { ...msg.message };
      if (live && live.tools) finalMsg.tools = live.tools;
      if (live) chat.messages.splice(chat.messages.length - 1, 1, finalMsg);
      else chat.messages.push(finalMsg);
      // The optimistic user message was born client-side without a turn_id;
      // the answer carries the shared one — backfill so the turn is deletable.
      if (finalMsg.turn_id) {
        const u = [...chat.messages].reverse().find(m => m.role === "user" && !m.turn_id);
        if (u) u.turn_id = finalMsg.turn_id;
      }
      chat.streaming = false;
      if (msg.meta) { chat.title = msg.meta.title || chat.title; chat.context = msg.meta.context || chat.context; }
      send({ type: "list" });  // the turn just touched title/updated
      break;
    }
    // Late LLM retitle — lands seconds after done, replacing the truncated
    // placeholder wherever it's on screen (header + history list).
    case "title": {
      if (msg.conv_id === chat.convId) chat.title = msg.title;
      const c = chat.convs.find(x => x.id === msg.conv_id);
      if (c) c.title = msg.title;
      break;
    }
    case "error": {
      if (msg.conv_id && msg.conv_id !== chat.convId) break;
      const live = streamingMsg();
      // An empty placeholder is noise; one with partial text keeps what arrived
      if (live && !live.content && !(live.tools || []).length)
        chat.messages.pop();
      else if (live) delete live._streaming;
      // Only a dead send flags the question — errors from delete/open arrive
      // outside a stream and have no pending user message.
      if (chat.streaming) markPendingFailed();
      chat.streaming = false;
      showToast(`Agent: ${msg.error}`);
      break;
    }
  }
}

/* ---- Actions the components call ---- */

export function newChat() {
  if (store.chat.streaming) { showToast("A reply is streaming — stop it first"); return; }
  if (!store.chat.online) {
    showToast(store.demo ? "New chat needs the agent service (demo)" : "Agent service offline");
    return;
  }
  send({ type: "new", context: currentContext() });
  focusChat();
}

/* Restore the conversation from the last app session. Called once after the
   workspace snapshot lands; the actual open is deferred to the next "convs"
   frame so we never trust a conv id the server can't back. */
let restoreConvId = null;
export function restoreChat(convId) {
  if (!convId || store.chat.convId === convId) return;
  restoreConvId = convId;
  // The list may already be on screen (WS beat the snapshot) — re-ask so the
  // convs handler runs again with the pending id.
  if (store.chat.online) send({ type: "list" });
}

export function openConv(convId) {
  if (store.chat.streaming) { showToast("A reply is streaming — stop it first"); return; }
  if (!store.chat.online) {
    store.historyOpen = false;
    showToast("Agent service offline" + (store.demo ? " (demo)" : ""));
    return;
  }
  send({ type: "open", conv_id: convId });
}

/* One user turn. Returns true when the composer should clear.
   The optimistic message mirrors what the server will persist: the typed
   text as content, pills/quotes under custom.display — one render path in
   ChatMessage.vue whether the message is fresh or reloaded from disk. */
export function sendMessage(text, pills, quotes) {
  const chat = store.chat;
  if (chat.streaming) return false;
  if (!chat.online) {
    if (store.demo) { demoTurn(text, pills, quotes); return true; }
    showToast("Agent service offline — chat is unavailable");
    return false;
  }
  if (!store.currentModel) {
    showToast("No model configured — pick one in Settings");
    return false;
  }
  if (!chat.convId) { showToast("Still connecting — try again in a second"); return false; }
  const m = { role: "user", content: text,
              custom: { display: { text, pills: pills || [], quotes: quotes || [] } } };
  chat.messages.push(m);
  chat.streaming = true;
  // The socket can die between the online check and here — don't fail silently
  if (!send({ type: "send", conv_id: chat.convId, model: store.currentModel, text, pills, quotes })) {
    chat.streaming = false;
    m._failed = true;
  }
  return true;
}

/* Resend a failed user message (the red "!"). The original send never made
   it into the transcript, so this is a plain send of the same text + pills;
   the message moves to the tail — where the server will append the turn. */
export function retrySend(m) {
  const chat = store.chat;
  if (chat.streaming) { showToast("A reply is streaming — stop it first"); return; }
  if (!chat.online) { showToast("Agent service offline — can't retry yet"); return; }
  if (!store.currentModel) { showToast("No model configured — pick one in Settings"); return; }
  delete m._failed;
  const i = chat.messages.indexOf(m);
  if (i >= 0) chat.messages.splice(i, 1);
  chat.messages.push(m);
  chat.streaming = true;
  const d = (m.custom && m.custom.display) || { text: m.content, pills: m.pills || [], quotes: [] };
  if (!send({ type: "send", conv_id: chat.convId, model: store.currentModel,
              text: d.text, pills: d.pills, quotes: d.quotes })) {
    chat.streaming = false;
    m._failed = true;
  }
}

export function cancelStream() {
  if (store.chat.convId) send({ type: "cancel", conv_id: store.chat.convId });
}

/* Delete one whole turn — the server cascades over every message sharing the
   turn_id (question + tool rounds + answer) and replies with the refreshed
   conversation, which the "conv" handler simply re-renders. */
export function deleteTurn(turnId) {
  if (store.chat.streaming) { showToast("A reply is streaming — stop it first"); return; }
  if (!store.chat.online) { showToast("Agent service offline"); return; }
  if (!turnId) { showToast("This message isn't saved yet"); return; }
  send({ type: "delete", conv_id: store.chat.convId, turn_id: turnId });
}

/* ?demo=1 without the agent: keep the send loop feeling alive, no network. */
function demoTurn(text, pills, quotes) {
  store.chat.messages.push({ role: "user", content: text,
    custom: { display: { text, pills: pills || [], quotes: quotes || [] } } });
  const n = (pills || []).length;
  setTimeout(() => {
    store.chat.messages.push({
      role: "assistant",
      content: `On it — ${n ? `reading ${n} attached item${n > 1 ? "s" : ""}… ` : ""}` +
        `*(demo reply · ${modelLabel(store.currentModel) || "no model configured"})*`,
    });
  }, 700);
}
