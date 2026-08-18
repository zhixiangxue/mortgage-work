/* ================= Agent Runtime (developer-facing view) =================
   Thin service browser for local/runtime infrastructure. Detail pages are
   mount points: the real db browsers are embedded as iframes here. */
import { reactive } from "vue";

export const SERVICES = reactive([
  { doc: "svc_qdrant",  name: "qdrant",   meta: "vector · :6333", status: "up" },
  { doc: "svc_falkor",  name: "falkordb", meta: "graph · :6379",  status: "up" },
  { doc: "svc_rqlite",  name: "rqlite",   meta: "sql · :4001",    status: "up" },
  { doc: "svc_redis",   name: "redis",    meta: "queue · :6380",  status: "up" },
  { doc: "svc_console", name: "console",  meta: "log tail",       status: "up" },
]);

/* Mount-point placeholder: the real UI drops in here later */
const mount = (title, note) => `
  <div class="mount-ph">
    <div class="mbox">
      <div class="mtitle">${title}</div>
      <div class="mnote">${note}</div>
    </div>
  </div>`;

/* Loopback URLs of the data browsers — all four are local viewer servers
   app.py spawns (falkordb / rqlite / qdrant / redis). app.py injects the real
   hosts/ports as window.__SERVICES__ (sourced from config.py/.env), and only
   for viewers whose data store is actually configured; these defaults match
   config.py so the Vite dev preview also works when the viewer servers are
   started by hand. */
const VIEWER_DEFAULTS = {
  qdrant: "http://127.0.0.1:19789",
  falkordb: "http://127.0.0.1:19787",
  rqlite: "http://127.0.0.1:19788",
  redis: "http://127.0.0.1:19790",
};

export function viewerSrc(name) {
  const injected = typeof window !== "undefined" && window.__SERVICES__;
  if (!injected) return VIEWER_DEFAULTS[name]; // Vite preview, no app injection
  // Inside the app, an absent key means app.py never configured/spawned that
  // viewer (.env block missing) — return null so the caller shows a
  // "not configured" plate instead of probing a dead port.
  return injected[name] || null;
}

/* Whether app.py told us a viewer exists. No injection (Vite preview) counts
   as "all present" so the dev preview keeps rendering every row. */
export function viewerAvailable(name) {
  const injected = typeof window !== "undefined" && window.__SERVICES__;
  return !injected || Boolean(injected[name]);
}

export const AGENT_DOCS = {
  // Data stores open their real browser in an iframe (frame -> viewerSrc key).
  // Badge SVC = live service surface, not a file type.
  svc_qdrant: {
    label: "qdrant", badge: "svc", crumb: ["runtime", "services", "qdrant"],
    frame: "qdrant",
  },
  svc_falkor: {
    label: "falkordb", badge: "svc", crumb: ["runtime", "services", "falkordb"],
    frame: "falkordb",
  },
  svc_rqlite: {
    label: "rqlite", badge: "svc", crumb: ["runtime", "services", "rqlite"],
    frame: "rqlite",
  },
  svc_redis: {
    label: "redis", badge: "svc", crumb: ["runtime", "services", "redis"],
    frame: "redis",
  },
  svc_console: {
    label: "console", badge: "svc", crumb: ["runtime", "services", "console"],
    pane: "console",
  },
};
