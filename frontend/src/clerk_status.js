/* Clerk status over SSE (agent_service.py → /clerk/stream).
   Owns an EventSource that receives {state, client, phase, message}
   pushes and writes them into store.clerk so the StatusBar and tree
   agent dots react immediately.  The EventSource auto-reconnects on
   drop — no reconnect loop to maintain. */

import { store } from "./store.js";

const DEFAULT_BASE = "http://127.0.0.1:8791";

// Log to runtime.log via the pywebview bridge so the user can read it
// without opening browser DevTools.  Also echoes to console.log.
function flog(level, msg) {
  console[level](msg);
  const api = window.pywebview && window.pywebview.api;
  if (api && api.log_frontend) {
    try { api.log_frontend(level === "error" || level === "warn" ? level : "info", msg); }
    catch { /* bridge not ready yet */ }
  }
}

function sseUrl() {
  if (window.__SERVICES__ && window.__SERVICES__.agent) {
    return window.__SERVICES__.agent.replace("/ws", "/clerk/stream").replace("ws://", "http://");
  }
  return DEFAULT_BASE + "/clerk/stream";
}

let es = null;
let _retries = 0;

export function initClerkStatus() {
  if (es) {
    try { es.close(); } catch { /* already closed */ }
  }
  const url = sseUrl();
  _retries++;
  flog("log", "[clerk] EventSource #" + _retries + " → " + url);
  try {
    es = new EventSource(url);
  } catch (e) {
    flog("error", "[clerk] EventSource constructor failed: " + e);
    setTimeout(initClerkStatus, 5000);
    return;
  }

  es.onopen = () => {
    flog("log", "[clerk] SSE connected, readyState=" + es.readyState);
    _retries = 0;
  };

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      flog("log", "[clerk] SSE ← state=" + data.state
        + (data.client ? " client=" + data.client : "")
        + (data.phase ? " phase=" + data.phase : "")
        + (data.message ? " msg=" + data.message : ""));
      store.clerk = {
        state: data.state || "idle",
        client: data.client || null,
        phase: data.phase || "",
        message: data.message || "",
      };
      if (data.state === "done" || data.state === "idle") {
        clearTimeout(es._doneTimer);
        es._doneTimer = setTimeout(() => {
          store.clerk = { state: "idle", client: null, phase: "", message: "" };
        }, 3000);
      }
    } catch { /* ignore malformed SSE data */ }
  };

  es.onerror = () => {
    flog("warn", "[clerk] SSE error, readyState=" + (es ? es.readyState : "null"));
    if (es && es.readyState === EventSource.CLOSED) {
      es.close();
      es = null;
      setTimeout(initClerkStatus, 5000);
    }
  };
}
