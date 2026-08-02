/* Window-global registry. Two consumers:
   1. The Python side — native menu actions call these via evaluate_js()
      (showToast / goHome / switchView / togglePanel / focusChat / setModel).
   2. v-html mock content (doc pages) whose inline onclick handlers can only
      resolve globals — same contract as the pre-Vue page. */
import {
  showToast, switchView, closeClient, togglePanel, focusChat,
  setModel, openDoc, setSyncState, applySnapshot, refreshOpenDocs,
  setIndexingState, paintIndexing,
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
    // Indexing state events (index/indexer.py → evaluate_js)
    setIndexingState,
    paintIndexing,
    // Filesystem watcher: disk changed → merge a fresh snapshot (app.py)
    applySnapshot,
    // Watcher fired but the tree is unchanged — an open file's bytes may
    // still have moved (agent/external write to an already-modified file)
    refreshOpenDocs,
    // v-html inline handlers (mock doc pages)
    openDoc,
  });
}
