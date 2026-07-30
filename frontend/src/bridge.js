/* Window-global registry. Two consumers:
   1. The Python side — native menu actions call these via evaluate_js()
      (showToast / goHome / switchView / togglePanel / focusChat / setModel).
   2. v-html mock content (doc pages, chat threads) whose inline onclick
      handlers can only resolve globals — same contract as the pre-Vue page. */
import {
  showToast, switchView, closeClient, togglePanel, focusChat,
  setModel, openDoc, setSyncState, applySnapshot,
} from "./store.js";

/* ---- Per-message actions injected by ChatPanel's decorator ---- */

function copyMsg(btn) {
  const text = btn.closest(".msg").querySelector(".bubble").innerText;
  navigator.clipboard && navigator.clipboard.writeText(text);
  showToast("Copied to clipboard");
}

function delMsg(btn) {
  btn.closest(".msg").remove();
  showToast("Message deleted (demo)");
}

export function registerGlobals() {
  Object.assign(window, {
    // Python menu hooks
    showToast,
    toastMsg: showToast,
    goHome: closeClient,
    switchView,
    togglePanel,
    focusChat,
    setModel,
    // Sync-engine state events (workrepo.py → evaluate_js)
    setSyncState,
    // Filesystem watcher: disk changed → merge a fresh snapshot (app.py)
    applySnapshot,
    // v-html inline handlers
    openDoc,
    copyMsg,
    delMsg,
  });
}
