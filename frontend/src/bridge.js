/* Window-global registry. Two consumers:
   1. The Python side — native menu actions call these via evaluate_js()
      (showToast / goHome / switchView / togglePanel / focusChat / setModel).
   2. v-html mock content (doc pages) whose inline onclick handlers can only
      resolve globals — same contract as the pre-Vue page. */
import {
  showToast, switchView, closeClient, togglePanel, focusChat,
  setModel, openDoc, setSyncState, applySnapshot, refreshOpenDocs,
  setKnowledgeState, setKnowledgeRows, applyAppConfig,
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
    // Knowledge Base state events (index/indexer.py → evaluate_js)
    setKnowledgeState,
    setKnowledgeRows,
    // Filesystem watcher: disk changed → merge a fresh snapshot (app.py)
    applySnapshot,
    // Watcher fired but the tree is unchanged — an open file's bytes may
    // still have moved (agent/external write to an already-modified file)
    refreshOpenDocs,
    // Runtime mode gates developer-only surfaces (Runtime, inspectors).
    applyAppConfig,
    // v-html inline handlers (mock doc pages)
    openDoc,
    // Connector bridge — pywebview.api wrappers for settings + messaging
    readConnectors: () => window.pywebview.api.read_connectors(),
    saveConnector: (p, f) => window.pywebview.api.save_connector(p, f),
    removeConnector: (p) => window.pywebview.api.remove_connector(p),
    connectorStatus: () => window.pywebview.api.connector_status(),
    connectorHistory: (p, c, l) => window.pywebview.api.connector_history(p, c, l),
    connectorConversations: (p) => window.pywebview.api.connector_conversations(p),
    connectorSend: (p, c, t) => window.pywebview.api.connector_send(p, c, t),
    connectorAttachment: (path) => window.pywebview.api.connector_attachment(path),
    connectorOpenAttachment: (path) => window.pywebview.api.connector_open_attachment(path),
  });
}
