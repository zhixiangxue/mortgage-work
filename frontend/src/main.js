import { createApp, watch } from "vue";
import App from "./App.vue";
import "./styles/global.css";
import { registerGlobals } from "./bridge.js";
import { initChatWS, restoreChats } from "./chatws.js";
import { initClerkStatus } from "./clerk_status.js";
import { store, showWelcome, hydrateWorkspace, loadDemoData, showToast, initTheme, loadModels,
         restoreSession, sessionState, setSyncState, setUpdateState, SYNC_TIMEOUT_MS } from "./store.js";

// Window globals must exist before any v-html inline handler can fire
registerGlobals();
// First-run progress pushed from Python (evaluate_js): clone / pull / restore
// stages narrate themselves on the boot overlay, so the curtain shows WHAT the
// backend is doing instead of a frozen screen. Registered before the bridge
// exists so the very first push lands.
window.setBootState = (stage, detail = "") => {
  store.bootStage = { stage, detail };
};
// Paint in the remembered theme before the first frame, not after it
initTheme();
// Initial state: empty editor + daily briefing chat (sidebar shows the client list)
showWelcome();

createApp(App).mount("#app");

// The agent WS is independent of the pywebview bridge — the service is a
// separate local server, so chat also works on the plain :5273 preview when
// the dev stack is up. The URL re-resolves per attempt, so app.py's late
// window.__SERVICES__ injection is picked up by the first retry.
// Deferred to pullWorkspace: conversations live in the user's repo, so a
// logged-out boot has nothing to talk about — connecting early just buys an
// "not logged in" toast. initChatWS is idempotent (guards against re-entry).
// Clerk SSE — same service, separate endpoint. The EventSource auto-reconnects.
initClerkStatus();

/* Pull the real workspace from the backend. The boot overlay holds its
   curtain until bootDone flips — the animation ends on real data, not a timer.
   In a plain browser (vite without pywebview) the fallback below releases the
   overlay into an explicitly-offline shell, or demo data if ?demo=1 asks. */
function pullWorkspace() {
  // initTheme() ran before the bridge existed, so the native title bar never
  // heard about a light theme. Re-apply now that there's someone to tell.
  initTheme();
  // settings.yaml lives outside the repo, so it loads on its own schedule — a
  // broken workspace shouldn't hide the models you configured.
  loadModels();
  window.pywebview.api.workspace_snapshot().then(snap => {
    if (snap && snap.auth === "required") {
      // No session on this machine — the login screen replaces the shell.
      // bootDone releases the boot curtain's timers; showLogin hides it.
      store.showLogin = true;
      store.bootDone = true;
      return;
    }
    if (snap && snap.error) {
      // Repo problems arrive as data; surface them without faking a workspace
      store.bootError = snap.error;
      showToast(`Workspace: ${snap.error}`);
    } else if (snap) {
      // A session exists — the chat socket may connect now (idempotent;
      // cold boot and post-login boot both land here exactly once each).
      initChatWS();
      hydrateWorkspace(snap);
      // Pick up where the last session left off — tabs, focus, conversation.
      // Once, on boot: the background rehydrates must not replay it.
      restoreSession(snap.session);
      restoreChats(snap.session);
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

function loadWorkspace() {
  if (loadWorkspace.started) return; // event + poll may both fire
  loadWorkspace.started = true;
  pullWorkspace();
}

/* LoginScreen's exit door: a fresh session just landed in the keychain, so
   run the exact same boot path — snapshot → hydrate → background sync. The
   first snapshot after a sign-up usually triggers the clone, and the boot
   overlay narrates it exactly like a first launch. */
export function bootAfterLogin() {
  store.showLogin = false;
  store.bootError = "";
  store.bootDone = false;
  pullWorkspace();
}

/* The boot-gate retry button: the workspace failed to load (no repo yet) and
   the user pressed RETRY. This is the one place allowed to do the whole slow
   round — boot_retry clones/pulls, flushes pending work, and (on success)
   hands back a full snapshot for the same rehydrate path boot uses. */
export function retryBoot() {
  if (store.bootRetrying || !window.pywebview) return;
  store.bootRetrying = true;
  window.pywebview.api.boot_retry().then(snap => {
    store.bootRetrying = false;
    if (snap && !snap.error) {
      store.bootError = "";
      initChatWS();  // RETRY revived the workspace — chat may connect now too
      hydrateWorkspace(snap);
      restoreSession(snap.session);
      restoreChats(snap.session);
      watchSession();
      syncInBackground();
      store.bootDone = true;
    } else {
      store.bootError = (snap && snap.error) || "boot retry failed";
    }
  }).catch(e => {
    store.bootRetrying = false;
    store.bootError = `bridge call failed: ${(e && e.message) || e}`;
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
/* One-shot read of the updater state once the bridge exists — the Python
   side pushes every change after this, but a state reached before the page
   loaded (boot check racing the window) would otherwise never arrive. */
function pullUpdateStatus() {
  if (pullUpdateStatus.done || !window.pywebview?.api?.update_status) return;
  pullUpdateStatus.done = true;
  window.pywebview.api.update_status().then(s => setUpdateState(s)).catch(() => {});
}
if (window.pywebview) { loadWorkspace(); pullUpdateStatus(); }
else {
  window.addEventListener("pywebviewready", () => pullUpdateStatus(), { once: true });
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
// No bridge after the first moments: the overlay narrates the wait instead of
// an early fake error — pywebview injects seconds after the page loads on a
// cold first run, and calling that window a failure was the whole problem.
// Only a genuinely absent backend (browser tab, or a desktop launch whose
// bridge never attached) escalates to an error, and only after a long grace.
setTimeout(() => {
  if (!store.bootDone && !window.pywebview) {
    if (new URLSearchParams(location.search).has("demo")) loadDemoData();
    else store.bootStage = { stage: "waiting", detail: "waiting for desktop backend…" };
  }
}, 1500);
setTimeout(() => {
  if (!store.bootDone && !window.pywebview &&
      !new URLSearchParams(location.search).has("demo")) {
    store.bootError = "backend not responding — restart the app";
    store.bootDone = true;
  }
}, 60000);
