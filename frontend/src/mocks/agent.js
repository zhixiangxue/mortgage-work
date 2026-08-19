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

/* Loopback URLs of the data browsers — all four are standalone viewer
   servers from the browser/ unit (own pyproject/.env, started with
   browser/serve.sh). The app never spawns them and never reads their
   config; it only borrows an iframe slot to display them. These ports
   mirror browser/config.py's defaults, and DocViewer's health probe
   decides whether each iframe actually loads (viewer not started =
   "unreachable", started = renders). */
const VIEWER_DEFAULTS = {
  qdrant: "http://127.0.0.1:19789",
  falkordb: "http://127.0.0.1:19787",
  rqlite: "http://127.0.0.1:19788",
  redis: "http://127.0.0.1:19790",
};

export function viewerSrc(name) {
  return VIEWER_DEFAULTS[name];
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
