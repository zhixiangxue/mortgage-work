import { createApp, watch } from "vue";
import App from "./App.vue";
import "./styles/global.css";
import { registerGlobals } from "./bridge.js";
import { initChatWS, restoreChat } from "./chatws.js";
import { store, showWelcome, hydrateWorkspace, loadDemoData, showToast, initTheme, loadModels,
         restoreSession, sessionState, setSyncState, SYNC_TIMEOUT_MS } from "./store.js";

// Window globals must exist before any v-html inline handler can fire
registerGlobals();
// Paint in the remembered theme before the first frame, not after it
initTheme();
// Initial state: empty editor + daily briefing chat (sidebar shows the client list)
showWelcome();

createApp(App).mount("#app");

// The agent WS is independent of the pywebview bridge — the service is a
// separate local server, so chat also works on the plain :5273 preview when
// the dev stack is up. The URL re-resolves per attempt, so app.py's late
// window.__SERVICES__ injection is picked up by the first retry.
initChatWS();

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
      // Pick up where the last session left off — tabs, focus, conversation.
      // Once, on boot: the background rehydrates must not replay it.
      restoreSession(snap.session);
      restoreChat(snap.session && snap.session.conv);
      watchSession();
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

/* Persist the session as it changes — armed only after restore so the boot
   sequence can't clobber the file with a half-hydrated state. Debounced: tab
   flurries collapse into one write, and losing the last 800ms on a hard kill
   costs a click, not work. */
function watchSession() {
  let timer = null;
  watch(() => JSON.stringify(sessionState()), () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      window.pywebview.api.save_session(sessionState()).catch(() => {});
    }, 800);
  });
}

/* Boot skipped the git pull to open instantly; fetch remote changes now and
   rehydrate quietly. The app is already usable at this point, so nothing here
   is allowed to matter: an unreachable remote (blocked network, no wifi in the
   demo room) just parks the status bar on the local copy, and the click on that
   indicator is the retry. */
function syncInBackground() {
  setSyncState("busy");
  // Python bounds every git step; this only catches "the bridge never answered".
  const guard = setTimeout(() => setSyncState("offline", "0"), SYNC_TIMEOUT_MS);
  window.pywebview.api.sync_workspace().then(snap => {
    clearTimeout(guard);
    if (snap && snap.error) setSyncState("offline", "0");
    else if (snap) {
      hydrateWorkspace(snap);
      // The sync engine's own push/commit state (setSyncState from Python) is
      // more precise than anything we could infer here — only fill in the
      // "never reached the remote" case it can't distinguish.
      if (snap.offline) setSyncState("offline", "0");
    }
  }).catch(() => {
    clearTimeout(guard);
    setSyncState("offline", "0");
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
