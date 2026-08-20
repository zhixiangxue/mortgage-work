<script setup>
import { computed, onMounted, ref } from "vue";
import { store, docs, showToast } from "../store.js";
import { modelUri, costFor } from "../pricing.js";

const doc = computed(() => docs[store.active]);
const convId = computed(() => doc.value?.convId || store.chat.convId || "");
const loading = ref(false);
const error = ref("");
const data = ref(null);
const rawMap = new Map();
let rawSeq = 0;

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c]));
}
function fmtNum(n) { return Number(n || 0).toLocaleString(); }
function money(n) { return Number.isFinite(n) ? "$" + n.toFixed(n < 0.01 ? 4 : 2) : "—"; }
function shortId(s) { s = String(s || ""); return s.length > 12 ? s.slice(0, 8) + "…" : s; }
function usageOf(m) { return (m?.metadata && m.metadata.usage) || {}; }
function stashRaw(obj) { const id = String(rawSeq++); rawMap.set(id, JSON.stringify(obj, null, 2)); return id; }

/* Model identification and costing live in pricing.js — shared with the
   usage panel so both surfaces price identically. */

const messages = computed(() => data.value?.messages || []);
const meta = computed(() => data.value?.meta || {});
const turns = computed(() => new Set(messages.value.map(m => m.turn_id).filter(Boolean)).size);
const toolCalls = computed(() => messages.value.reduce((n, m) => n + (Array.isArray(m.tool_calls) ? m.tool_calls.length : 0), 0));

const usageRows = computed(() => {
  const by = new Map();
  for (const m of messages.value) {
    if (m.role !== "assistant") continue;
    const u = usageOf(m);
    if (!u || !Object.keys(u).length) continue;
    const uri = modelUri(m.metadata || {}) || modelUri(meta.value || {}) || meta.value.model || "unknown";
    const b = by.get(uri) || { uri, calls: 0, prompt: 0, completion: 0, cacheW: 0, cacheR: 0, total: 0 };
    const pt = u.prompt_tokens || 0, ct = u.completion_tokens || 0;
    const cw = u.cache_creation_input_tokens || 0, cr = u.cache_read_input_tokens || 0;
    b.calls += 1; b.prompt += pt; b.completion += ct; b.cacheW += cw; b.cacheR += cr;
    b.total += u.total_tokens || pt + ct + cw + cr;
    by.set(uri, b);
  }
  return [...by.values()].sort((a, b) => b.total - a.total);
});

const pricedRows = computed(() => {
  let total = 0, unknown = false;
  const rows = usageRows.value.map(b => {
    const c = costFor(b, data.value?.prices || {});
    if (c.known) total += c.cost; else unknown = true;
    return { ...b, cost: c.cost, costKnown: c.known, priceKey: c.key };
  });
  return { rows, total, unknown };
});

const grouped = computed(() => {
  const groups = [];
  let cur = null;
  for (const m of messages.value) {
    const tid = m.turn_id || null;
    if (!cur || cur.turn_id !== tid) { cur = { turn_id: tid, messages: [] }; groups.push(cur); }
    cur.messages.push(m);
  }
  return groups;
});

function toolIndex() {
  const idx = new Map();
  for (const m of messages.value) if (m.role === "assistant" && Array.isArray(m.tool_calls)) {
    for (const tc of m.tool_calls) {
      const fn = tc.function || {};
      if (tc.id) idx.set(tc.id, { name: fn.name || tc.name || "?", arguments: fn.arguments || tc.arguments || "" });
    }
  }
  return idx;
}

function contentText(c) {
  if (c == null) return "";
  if (typeof c === "string") return c;
  if (Array.isArray(c)) return c.map(p => p && p.type === "text" ? p.text : JSON.stringify(p, null, 2)).join("\n\n");
  return JSON.stringify(c, null, 2);
}
function prettyArgs(s) { try { return JSON.stringify(JSON.parse(s), null, 2); } catch { return String(s || ""); } }
function modelAndTokens(m) {
  const uri = modelUri(m.metadata || {}), u = usageOf(m);
  const pt = u.prompt_tokens || 0, ct = u.completion_tokens || 0, cr = u.cache_read_input_tokens || 0, cw = u.cache_creation_input_tokens || 0;
  return { uri, pt, ct, cache: cr + cw };
}
function copyRaw(id) {
  const text = rawMap.get(String(id)) || data.value?.raw || "";
  navigator.clipboard?.writeText(text);
}

async function refresh() {
  if (!convId.value) { error.value = "No conversation open"; return; }
  if (!window.pywebview?.api?.load_conv_inspector) { error.value = "Conversation inspector needs the desktop app"; return; }
  loading.value = true; error.value = ""; rawMap.clear(); rawSeq = 0;
  try {
    const res = await window.pywebview.api.load_conv_inspector(convId.value);
    if (!res || res.error) throw new Error((res && res.error) || "load failed");
    data.value = res;
  } catch (e) {
    error.value = e.message || String(e);
    showToast(`Inspector: ${error.value}`);
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);
</script>

<template>
  <div class="conv-inspector">
    <aside class="ci-side">
      <div class="ci-bar-group ci-bar-brand">
        <span class="brand-name">Conv Inspector</span>
        <span class="brand-sub">{{ loading ? "refreshing…" : `${messages.length} messages` }}</span>
        <button @click="refresh">Refresh</button>
        <button @click="copyRaw('')">Copy raw</button>
      </div>
      <div class="ci-bar-group ci-bar-summary">
        <span class="ci-bar-label">msgs</span><b>{{ messages.length }}</b>
        <span class="ci-bar-label">turns</span><b>{{ turns }}</b>
        <span class="ci-bar-label">tools</span><b>{{ toolCalls }}</b>
        <span class="ci-bar-label">jsonl</span><b class="ci-bar-num">{{ fmtNum((data?.raw || "").length) }}</b>
      </div>
      <div class="ci-bar-group ci-bar-turns">
        <span class="ci-bar-label">turns</span>
        <a v-for="(g, i) in grouped.filter(x => x.turn_id)" :key="g.turn_id" :href="`#turn-${i + 1}`" class="turn-link">{{ String(i + 1).padStart(2, "0") }}</a>
      </div>
      <div class="ci-bar-group ci-bar-pricing" v-if="data?.prices">
        <span class="ci-bar-label">pricing</span>
        <span class="brand-sub">{{ data?.prices?.updated || "" }} · {{ data?.prices?.note || "" }}</span>
      </div>
    </aside>

    <main class="ci-main">
      <header class="ci-head">
        <div class="title"><h1>{{ meta.title || data?.conv_id || convId || "Conversation" }}</h1><div class="meta">{{ data?.path || "" }} · model {{ modelUri(meta) || "unknown" }}</div></div>
        <div class="stats" v-if="pricedRows.rows.length">
          <div class="stats-grid">
            <div class="hdr">model_uri</div><div class="hdr num">calls</div><div class="hdr num">in</div><div class="hdr num">out</div><div class="hdr num">cache_w</div><div class="hdr num">cache_r</div><div class="hdr num">total</div><div class="hdr num">cost</div>
            <template v-for="r in pricedRows.rows" :key="r.uri">
              <div>{{ r.uri }} <span v-if="r.priceKey && r.priceKey !== r.uri" class="unknown">priced as {{ r.priceKey }}</span></div>
              <div class="num">{{ fmtNum(r.calls) }}</div><div class="num">{{ fmtNum(r.prompt) }}</div><div class="num">{{ fmtNum(r.completion) }}</div><div class="num">{{ fmtNum(r.cacheW) }}</div><div class="num">{{ fmtNum(r.cacheR) }}</div><div class="num">{{ fmtNum(r.total) }}</div><div class="num money" :class="{ unknown: !r.costKnown }">{{ r.costKnown ? money(r.cost) : "unknown" }}</div>
            </template>
            <div>total</div><div></div><div></div><div></div><div></div><div></div><div></div><div class="num money">{{ money(pricedRows.total) }}{{ pricedRows.unknown ? " + unknown" : "" }}</div>
          </div>
        </div>
        <div v-else class="empty small">no llm usage metadata</div>
      </header>

      <div v-if="error" class="empty">{{ error }}</div>
      <div v-else-if="!data" class="empty">Loading conversation…</div>
      <div v-else class="content">
        <section v-for="(g, gi) in grouped" :key="gi" class="turn">
          <div class="turn-header" :id="g.turn_id ? `turn-${grouped.filter(x => x.turn_id).indexOf(g) + 1}` : null"><span class="turn-num">{{ g.turn_id ? String(grouped.filter(x => x.turn_id).indexOf(g) + 1).padStart(2, "0") : "setup" }}</span><span>{{ g.turn_id ? "turn" : "" }}</span><span class="turn-id">{{ shortId(g.turn_id) }}</span><span>{{ g.messages.length }} msg{{ g.messages.length === 1 ? "" : "s" }}</span></div>
          <div v-for="(m, mi) in g.messages" :key="mi" class="msg" :class="[`role-${m.role || 'unknown'}`, { 'tool-call-msg': m.role === 'assistant' && m.tool_calls?.length, 'tool-result': m.role === 'tool' }]">
            <div class="head"><span class="badge" :class="m.role === 'tool' ? 'role-resp' : (m.role === 'assistant' && m.tool_calls?.length ? 'role-req' : `role-${m.role || 'system'}-b`)">{{ m.role === 'tool' ? 'tool call response' : (m.role === 'assistant' && m.tool_calls?.length ? 'tool call request' : m.role) }}</span>
              <template v-if="m.role === 'assistant'"><span v-if="modelAndTokens(m).uri" class="model-tag">{{ modelAndTokens(m).uri }}</span><span v-if="modelAndTokens(m).pt || modelAndTokens(m).ct" class="tok">↓ {{ fmtNum(modelAndTokens(m).pt) }}</span><span v-if="modelAndTokens(m).pt || modelAndTokens(m).ct" class="tok">↑ {{ fmtNum(modelAndTokens(m).ct) }}</span><span v-if="modelAndTokens(m).cache" class="tok">cache {{ fmtNum(modelAndTokens(m).cache) }}</span></template>
              <span v-if="m.role === 'tool'" class="subtle">{{ shortId(m.tool_call_id) }}</span><button class="copy" @click="copyRaw(stashRaw(m))">raw</button>
            </div>
            <div v-if="m.role === 'tool' && toolIndex().get(m.tool_call_id)" class="tool-req-echo"><div class="echo-fn">{{ toolIndex().get(m.tool_call_id).name }}</div><pre>{{ prettyArgs(toolIndex().get(m.tool_call_id).arguments) }}</pre></div>
            <div v-if="m.role !== 'tool' && contentText(m.content)" class="body"><pre>{{ contentText(m.content) }}</pre></div>
            <div v-if="m.role === 'tool'" class="tool-body">{{ contentText(m.content) }}</div>
            <details v-for="tc in (m.tool_calls || [])" :key="tc.id" open><summary><span class="tool-name">{{ tc.function?.name || tc.name || "?" }}</span> <span class="subtle">{{ shortId(tc.id) }}</span></summary><pre>{{ prettyArgs(tc.function?.arguments || tc.arguments) }}</pre></details>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>

<style scoped>
.conv-inspector { flex:1; min-height:0; display:flex; flex-direction:column; background:var(--bg-editor); color:var(--text); }

/* top bar */
.ci-side { display:flex; flex-wrap:wrap; align-items:center; gap:0; border-bottom:1px solid var(--border); background:var(--bg-panel); flex-shrink:0; padding:4px 6px; }
.ci-bar-group { display:flex; align-items:center; gap:6px; padding:4px 10px; border-right:1px solid var(--border); white-space:nowrap; }
.ci-bar-group:last-child { border-right:none; }
.ci-bar-brand { gap:10px; }
.brand-name { font:700 11px var(--mono); letter-spacing:.12em; text-transform:uppercase; }
.brand-sub, .meta, .subtle, .tok { color:var(--text-3); font:10px var(--mono); }
.ci-bar-label { color:var(--text-4); font:9px var(--mono); letter-spacing:.1em; text-transform:uppercase; }
.ci-bar-summary b { color:var(--text-2); font:11px var(--mono); }
.ci-bar-num { font-variant-numeric:tabular-nums; }
.turn-link { color:var(--text-2); text-decoration:none; border:1px solid var(--border); padding:1px 4px; font:9px var(--mono); }
.turn-link:hover { border-color:var(--brand); color:var(--brand); }
.ci-bar-pricing { font-size:9px; }

/* main */
.ci-main { flex:1; min-height:0; overflow:auto; }
.ci-head { position:relative; border-bottom:1px solid var(--border); background:var(--bg-panel); }
.ci-head > .title { padding:14px 28px 0; }
.ci-head h1 { margin:0; font-size:16px; line-height:1.35; word-break:break-word; }
button { border:1px solid var(--border-soft); background:var(--bg-raise); color:var(--text-2); padding:7px 10px; font:10px var(--mono); letter-spacing:.1em; text-transform:uppercase; cursor:pointer; }
button:hover { border-color:var(--brand); color:var(--brand); }
.stats { margin-top:12px; overflow:auto; border-top:1px solid var(--border); }
.stats-grid { display:grid; grid-template-columns:minmax(140px,1fr) repeat(6,64px) 80px; font:11px var(--mono); }
.stats-grid > * { padding:7px 10px; border-bottom:1px solid var(--border); white-space:nowrap; }
.hdr { color:var(--text-4); font-weight:500; }
.num { text-align:right; font-variant-numeric:tabular-nums; }
.money { color:var(--brand); font-weight:700; }
.unknown { color:var(--text-4); }
.content { padding:22px 28px 80px; }
.turn { margin:0 0 24px; }
.turn-header { display:flex; align-items:center; gap:10px; border-top:1px solid var(--border-soft); padding:10px 0; color:var(--text-3); font:11px var(--mono); }
.turn-num { color:var(--text); font-weight:700; letter-spacing:.1em; }
.turn-id { color:var(--text-4); }
.msg { margin:10px 0 12px; border-left:3px solid var(--border-soft); padding:0 0 0 12px; }
.role-system { opacity:.78; } .role-user { border-color:var(--blue); } .role-assistant { border-color:var(--amber); background:linear-gradient(90deg,var(--tint-amber),transparent 42%); }
.tool-call-msg { border-color:var(--amber); } .tool-result { border-color:var(--green); }
.head { display:flex; align-items:center; gap:8px; min-height:24px; flex-wrap:wrap; }
.badge { color:var(--on-brand); padding:2px 6px; font:10px var(--mono); letter-spacing:.08em; text-transform:uppercase; background:var(--text-4); }
.role-user-b { background:var(--blue); } .role-assistant-b { background:var(--amber); } .role-system-b { background:var(--text-4); } .role-req { background:var(--amber); } .role-resp { background:var(--green); }
.model-tag { border:1px solid var(--border); padding:1px 5px; color:var(--text-2); font:10px var(--mono); }
.body { color:var(--text-2); font-size:13px; line-height:1.65; padding:5px 0 2px; }
pre, .tool-body { background:var(--bg-raise); border:1px solid var(--border); padding:10px; overflow:auto; font:11px/1.55 var(--mono); color:var(--text-2); white-space:pre-wrap; word-break:break-word; }
details { margin:8px 0; } summary { cursor:pointer; color:var(--text-2); font:11px var(--mono); }
.tool-name, .echo-fn { font-weight:700; color:var(--amber); }
.tool-req-echo { border:1px solid var(--border); background:var(--bg-hover); margin:8px 0; }
.echo-fn { padding:7px 10px; border-bottom:1px solid var(--border); font:700 11px var(--mono); }
.copy { margin-left:auto; padding:2px 6px; font-size:9px; }
.empty { padding:48px; color:var(--text-4); font:12px var(--mono); }
.empty.small { padding:12px 28px; }
</style>
