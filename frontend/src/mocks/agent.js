/* ================= Agent Runtime (developer-facing view) =================
   Deliberately thin: one main agent (subs are tools — observe them in traces,
   not in a sidebar), and the infra services. Detail pages are mount points:
   the real trace explorer / db browsers already exist and will be embedded
   (iframe / child webview) — no config prose, no fake dashboards here. */
import { reactive } from "vue";

/* Reactive: restart buttons flip these statuses live */
export const MAIN = reactive({ status: "running" }); // 'running' | 'restart'

export const SERVICES = reactive([
  { doc: "svc_qdrant",  name: "qdrant",   meta: "vector · :6333", status: "up" },
  { doc: "svc_falkor",  name: "falkordb", meta: "graph · :6379",  status: "up" },
  { doc: "svc_rqlite",  name: "rqlite",   meta: "sql · :4001",    status: "up" },
  { doc: "svc_redis",   name: "redis",    meta: "queue · :6380",  status: "up" },
  { doc: "svc_workers", name: "workers",  meta: "dramatiq × 4",   status: "busy" },
]);

/* Chat panel content when the runtime view is focused */
export const CHAT_AGENT = `
  <div class="msg ai">
    <div class="bubble">Runtime console. All services up · queue 3 jobs · 2/4 workers busy.
    Ask about a trace, or type <code class="inline">/restart</code>.</div>
  </div>`;

/* Mount-point placeholder: the real UI drops in here later */
const mount = (title, note) => `
  <div class="mount-ph">
    <div class="mbox">
      <div class="mtitle">${title}</div>
      <div class="mnote">${note}</div>
    </div>
  </div>`;

/* Loopback URLs of the data browsers — all three are local viewer servers
   app.py spawns (falkordb / rqlite / qdrant). app.py injects the real
   hosts/ports as window.__SERVICES__ (sourced from config.py/.env); these
   defaults match config.py so the Vite dev preview also works when the viewer
   servers are started by hand. */
const VIEWER_DEFAULTS = {
  qdrant: "http://127.0.0.1:8789",
  falkordb: "http://127.0.0.1:8787",
  rqlite: "http://127.0.0.1:9090",
  redis: "http://127.0.0.1:8790",
};

export function viewerSrc(name) {
  const injected = (typeof window !== "undefined" && window.__SERVICES__) || {};
  return injected[name] || VIEWER_DEFAULTS[name];
}

export const AGENT_DOCS = {
  ag_main: {
    label: "traces", badge: "ai", crumb: ["runtime", "main", "traces"],
    html: mount("TRACE EXPLORER",
      "Existing trace UI mounts here — iframe / child webview, keyed by run id.<br>" +
      "Every run: main agent plan → tool (sub-agent) calls → service hits, with timings."),
  },
  // Data stores open their real browser in an iframe (frame -> viewerSrc key)
  svc_qdrant: {
    label: "qdrant", badge: "yml", crumb: ["runtime", "services", "qdrant"],
    frame: "qdrant",
  },
  svc_falkor: {
    label: "falkordb", badge: "yml", crumb: ["runtime", "services", "falkordb"],
    frame: "falkordb",
  },
  svc_rqlite: {
    label: "rqlite", badge: "yml", crumb: ["runtime", "services", "rqlite"],
    frame: "rqlite",
  },
  svc_redis: {
    label: "redis", badge: "yml", crumb: ["runtime", "services", "redis"],
    frame: "redis",
  },
  svc_workers: {
    label: "workers", badge: "yml", crumb: ["runtime", "services", "workers"],
    html: mount("QUEUE DASHBOARD",
      "Worker pool view mounts here — per-worker state, queue depth, requeues.<br>" +
      "broker <code class='inline'>redis://localhost:6379</code> · 4 workers"),
  },
};
