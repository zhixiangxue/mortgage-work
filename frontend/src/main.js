import { createApp } from "vue";
import App from "./App.vue";
import "./styles/global.css";
import { registerGlobals } from "./bridge.js";
import { store, showWelcome, hydrateWorkspace, loadDemoData, showToast, initTheme, loadModels } from "./store.js";

// Window globals must exist before any v-html inline handler can fire
registerGlobals();
// Paint in the remembered theme before the first frame, not after it
initTheme();
// Initial state: empty editor + daily briefing chat (sidebar shows the client list)
showWelcome();

createApp(App).mount("#app");

/* Pull the real workspace from the backend. The boot overlay holds its
   curtain until bootDone flips — the animation ends on real data, not a timer.
   In a plain browser (vite without pywebview) the fallback below releases the
   overlay into an explicitly-offline shell, or demo data if ?demo=1 asks. */
function loadWorkspace() {
  if (loadWorkspace.started) return; // event + poll may both fire
  loadWorkspace.started = true;
  // initTheme() ran before the bridge existed, so the native title bar never
  // heard about a light theme. Re-apply now that there's someone to tell.
  initTheme();
  // models.yaml lives outside the repo, so it loads on its own schedule — a
  // broken workspace shouldn't hide the models you configured.
  loadModels();
  window.pywebview.api.workspace_snapshot().then(snap => {
    if (snap && snap.error) {
      // Repo problems arrive as data; surface them without faking a workspace
      store.bootError = snap.error;
      showToast(`Workspace: ${snap.error}`);
    } else if (snap) {
      hydrateWorkspace(snap);
      syncInBackground();
    } else {
      store.bootError = "empty workspace snapshot";
    }
    store.bootDone = true;
  }).catch(e => {
    // A rejected bridge call must never strand the app silently
    store.bootError = `bridge call failed: ${(e && e.message) || e}`;
    showToast(`Workspace: ${store.bootError}`);
    store.bootDone = true;
  });
}

/* Boot skipped the git pull to open instantly; fetch remote changes now and
   rehydrate quietly. Failures are non-fatal — local data is already live. */
function syncInBackground() {
  store.sync = { cls: "busy", label: "● SYNCING…" };
  window.pywebview.api.sync_workspace().then(snap => {
    if (snap && !snap.error) hydrateWorkspace(snap);
    store.sync = { cls: "ok", label: "● SYNCED · JUST NOW" };
  }).catch(() => {
    store.sync = { cls: "ok", label: "● OFFLINE · LOCAL COPY" };
  });
}
if (window.pywebview) loadWorkspace();
else {
  window.addEventListener("pywebviewready", loadWorkspace, { once: true });
  // Belt and braces: pywebviewready can fire BEFORE this module runs (bridge
  // injection races module eval). Poll a while so we never strand the app on
  // mock data with no error and no hint.
  let tries = 0;
  const poll = setInterval(() => {
    if (window.pywebview) { clearInterval(poll); loadWorkspace(); }
    else if (++tries > 40) clearInterval(poll); // ~10s: plain browser, give up
  }, 250);
}
// No bridge showed up — plain browser. Demo data is opt-in (?demo=1) so a
// stray browser tab can't pass for a working app: without the flag the shell
// boots empty and says so (boot overlay line + persistent status-bar flag).
setTimeout(() => {
  if (!store.bootDone && !window.pywebview) {
    if (new URLSearchParams(location.search).has("demo")) loadDemoData();
    else store.bootError = "browser preview, no backend — open the desktop app (?demo=1 for demo data)";
    store.bootDone = true;
  }
}, 900);
