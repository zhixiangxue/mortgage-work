/* Window-global registry. Two consumers:
   1. The Python side — native menu actions call these via evaluate_js()
      (showToast / goHome / switchView / togglePanel / focusChat / setModel).
   2. v-html mock content (doc pages) whose inline onclick handlers can only
      resolve globals — same contract as the pre-Vue page. */
import {
  showToast, switchView, closeClient, togglePanel, focusChat,
  setModel, openDoc, setSyncState, applySnapshot,
} from "./store.js";

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
    // v-html inline handlers (mock doc pages)
    openDoc,
  });
}
