<script setup>
import { computed, onMounted, ref } from "vue";
import { store, docs, showToast } from "../store.js";

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

function modelUri(meta = {}) {
  const pt = meta.provider_trace || {};
  const direct = meta.model_uri || meta.model_ref || meta.model_name || meta.model;
  const p = pt.resolved_provider || pt.provider || meta.provider;
  const m = pt.resolved_model || pt.model || direct;
  if (p && m && !String(m).includes("/")) return `${p}/${m}`;
  return m || p || null;
}

function normalizeModelKey(s) {
  return String(s || "")
    .trim()
    .toLowerCase()
    .replace(/^model:\/\//, "")
    .replace(/[?#].*$/, "")
    .replace(/:.+$/, "")
    .replace(/^models\//, "");
}

function canonicalPriceKey(uri, prices = {}) {
  if (!uri) return null;
  const models = prices.models || {}, aliases = prices.aliases || {};
  const modelKeys = Object.keys(models);
  const aliasKeys = Object.keys(aliases);
  const candidates = [];
  const raw = String(uri || "").trim();
  const providerColon = raw.match(/^(openai|anthropic|google|deepseek|moonshot|xai):(.+)$/i);
  const rawProvider = providerColon ? `${providerColon[1].toLowerCase()}/${providerColon[2]}` : raw;
  const norm = normalizeModelKey(rawProvider);
  candidates.push(raw, rawProvider, norm, norm.split("/").pop());
  for (const c of [...candidates]) {
    if (!c) continue;
    if (models[c]) return c;
    if (aliases[c] && models[aliases[c]]) return aliases[c];
  }
  const lowerModel = new Map(modelKeys.map(k => [normalizeModelKey(k), k]));
  const lowerAlias = new Map(aliasKeys.map(k => [normalizeModelKey(k), aliases[k]]));
  for (const c of candidates.map(normalizeModelKey)) {
    if (lowerModel.has(c)) return lowerModel.get(c);
    if (lowerAlias.has(c) && models[lowerAlias.get(c)]) return lowerAlias.get(c);
  }
  // Versioned model ids: openai/gpt-4o-2024-08-06 -> openai/gpt-4o.
  const prefix = modelKeys
    .slice()
    .sort((a, b) => b.length - a.length)
    .find(k => norm === normalizeModelKey(k) || norm.startsWith(normalizeModelKey(k) + "-"));
  if (prefix) return prefix;
  const model = norm.split("/").pop();
  const aliasPrefix = aliasKeys
    .slice()
    .sort((a, b) => b.length - a.length)
    .find(k => model === normalizeModelKey(k) || model.startsWith(normalizeModelKey(k) + "-"));
  return aliasPrefix && models[aliases[aliasPrefix]] ? aliases[aliasPrefix] : null;
}

function costFor(bucket, prices) {
  const key = canonicalPriceKey(bucket.uri, prices || {});
  const p = key && prices?.models ? prices.models[key] : null;
  if (!p) return { known: false, cost: NaN, key: null };
  const cost = (
    bucket.prompt * (p.input || 0) +
    bucket.completion * (p.output || 0) +
    bucket.cacheW * (p.cache_write ?? p.input ?? 0) +
    bucket.cacheR * (p.cache_read ?? p.input ?? 0)
  ) / 1_000_000;
  return { known: true, cost, key };
}

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
      <div class="brand"><div class="brand-name">Conv Inspector</div><div class="brand-sub">{{ loading ? "refreshing…" : `${messages.length} messages` }}</div></div>
      <div class="side-section"><div class="side-title">summary</div>
        <div class="metric"><span>messages</span><b>{{ messages.length }}</b></div>
        <div class="metric"><span>turns</span><b>{{ turns }}</b></div>
        <div class="metric"><span>tool calls</span><b>{{ toolCalls }}</b></div>
        <div class="metric"><span>jsonl</span><b>{{ fmtNum((data?.raw || "").length) }} chars</b></div>
      </div>
      <div class="side-section"><div class="side-title">turns</div><div class="turn-nav">
        <a v-for="(g, i) in grouped.filter(x => x.turn_id)" :key="g.turn_id" :href="`#turn-${i + 1}`">{{ String(i + 1).padStart(2, "0") }}</a>
      </div></div>
      <div class="side-section"><div class="side-title">pricing</div><div class="brand-sub">{{ data?.prices?.updated || "" }} · {{ data?.prices?.note || "" }}</div></div>
    </aside>

    <main class="ci-main">
      <header class="ci-head">
        <div class="title"><h1>{{ meta.title || data?.conv_id || convId || "Conversation" }}</h1><div class="meta">{{ data?.path || "" }} · model {{ modelUri(meta) || "unknown" }}</div></div>
        <div class="actions"><button @click="refresh">Refresh</button><button @click="copyRaw('')">Copy raw</button></div>
        <div class="stats" v-if="pricedRows.rows.length">
          <table><thead><tr><th>model_uri</th><th>calls</th><th>in</th><th>out</th><th>cache_w</th><th>cache_r</th><th>total</th><th>cost</th></tr></thead>
            <tbody><tr v-for="r in pricedRows.rows" :key="r.uri">
              <td><span class="model-tag">{{ r.uri }}</span> <span v-if="r.priceKey && r.priceKey !== r.uri" class="unknown">priced as {{ r.priceKey }}</span></td>
              <td class="num">{{ fmtNum(r.calls) }}</td><td class="num">{{ fmtNum(r.prompt) }}</td><td class="num">{{ fmtNum(r.completion) }}</td><td class="num">{{ fmtNum(r.cacheW) }}</td><td class="num">{{ fmtNum(r.cacheR) }}</td><td class="num">{{ fmtNum(r.total) }}</td><td class="num money" :class="{ unknown: !r.costKnown }">{{ r.costKnown ? money(r.cost) : "unknown" }}</td>
            </tr><tr><td>total</td><td colspan="6"></td><td class="num money">{{ money(pricedRows.total) }}{{ pricedRows.unknown ? " + unknown" : "" }}</td></tr></tbody></table>
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
.conv-inspector { flex:1; min-height:0; display:grid; grid-template-columns:260px minmax(0,1fr); background:var(--bg-editor); color:var(--text); }
.ci-side { height:100%; overflow:auto; border-right:1px solid var(--border); background:var(--bg-panel); }
.brand { padding:14px 18px; border-bottom:1px solid var(--border); }
.brand-name { font:700 12px var(--mono); letter-spacing:.14em; text-transform:uppercase; }
.brand-sub, .meta, .subtle, .tok { color:var(--text-3); font:10px var(--mono); }
.side-section { padding:14px 18px; border-bottom:1px solid var(--border); }
.side-title { color:var(--text-4); font:10px var(--mono); letter-spacing:.14em; text-transform:uppercase; margin-bottom:8px; }
.metric { display:flex; justify-content:space-between; gap:12px; padding:4px 0; font:11px var(--mono); color:var(--text-2); }
.metric span:first-child { color:var(--text-4); }
.turn-nav { display:flex; flex-wrap:wrap; gap:6px; }
.turn-nav a { color:var(--text-2); text-decoration:none; border:1px solid var(--border); padding:3px 6px; font:10px var(--mono); }
.turn-nav a:hover { border-color:var(--brand); color:var(--brand); }
.ci-main { min-width:0; min-height:0; overflow:auto; }
.ci-head { position:relative; border-bottom:1px solid var(--border); background:var(--bg-panel); }
.ci-head > .title, .actions { padding:14px 28px 0; }
.ci-head h1 { margin:0; font-size:16px; line-height:1.35; word-break:break-word; }
.actions { position:absolute; right:0; top:0; display:flex; gap:8px; }
button { border:1px solid var(--border-soft); background:var(--bg-raise); color:var(--text-2); padding:7px 10px; font:10px var(--mono); letter-spacing:.1em; text-transform:uppercase; cursor:pointer; }
button:hover { border-color:var(--brand); color:var(--brand); }
.stats { margin-top:12px; overflow:auto; border-top:1px solid var(--border); }
table { width:100%; border-collapse:collapse; font:11px var(--mono); }
th, td { padding:7px 10px; border-bottom:1px solid var(--border); text-align:left; white-space:nowrap; }
th { color:var(--text-4); font-weight:500; text-transform:uppercase; letter-spacing:.12em; font-size:9px; }
.num { text-align:right; font-variant-numeric:tabular-nums; }
.money { color:var(--brand); font-weight:700; }
.unknown { color:var(--text-4); }
.content { max-width:1080px; padding:22px 28px 80px; }
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
