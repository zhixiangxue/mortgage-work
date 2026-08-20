<script setup>
/* Usage — LLM token + cost statistics over the work-repo's conversations,
   per day × model. Visual contract: tmp/usage-panel-design.html. Data comes
   pre-aggregated from app.py's load_usage_stats (last 30 days); the 7/30-day
   switch filters client-side. Costing goes through pricing.js — the same code
   path as the conversation inspector. */
import { computed, onMounted, ref } from "vue";
import { showToast } from "../store.js";
import { costFor } from "../pricing.js";

const loading = ref(false);
const error = ref("");
const data = ref(null);
const rangeDays = ref(7);

function fmtNum(n) { return Number(n || 0).toLocaleString(); }
function money(n) { return Number.isFinite(n) ? "$" + n.toFixed(n < 0.01 ? 4 : 2) : "—"; }
/* Price source link: hand the URL to the OS browser through the bridge — a
   plain <a> would navigate the webview itself away from the app. */
function openPriceSource() {
  window.pywebview?.api?.open_url?.("https://token.app");
}
function compact(n) {
  return n >= 1e9 ? (n / 1e9).toFixed(1) + "B"
       : n >= 1e6 ? (n / 1e6).toFixed(1) + "M"
       : n >= 1e3 ? (n / 1e3).toFixed(1) + "K"
       : String(n);
}
/* Local date string YYYY-MM-DD, `days` ago — day buckets from the backend are
   local-time dates, so the cutoff must be computed the same way. */
function localDayOffset(days) {
  const d = new Date(Date.now() - days * 86400000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

async function load() {
  if (!window.pywebview?.api?.load_usage_stats) { error.value = "Usage needs the desktop app"; return; }
  loading.value = true; error.value = "";
  try {
    const res = await window.pywebview.api.load_usage_stats();
    if (!res || res.error) throw new Error((res && res.error) || "load failed");
    data.value = res;
  } catch (e) {
    error.value = e.message || String(e);
    showToast(`Usage: ${error.value}`);
  } finally {
    loading.value = false;
  }
}

/* Day groups within the selected range, each model row priced. A day's
   subtotal counts only the priced rows — unknown costs surface separately so
   a number never silently hides an unpriced model. */
const days = computed(() => {
  const cutoff = localDayOffset(rangeDays.value - 1);
  const out = [];
  for (const day of data.value?.days || []) {
    if (day.date < cutoff) continue;
    const models = day.models.map(m => ({ ...m, ...costFor(m, data.value?.prices || {}) }));
    const sub = models.reduce((a, m) => {
      a.calls += m.calls; a.prompt += m.prompt; a.completion += m.completion;
      a.cacheW += m.cacheW; a.cacheR += m.cacheR; a.total += m.total;
      if (m.known) a.cost += m.cost; else a.unknown = true;
      return a;
    }, { calls: 0, prompt: 0, completion: 0, cacheW: 0, cacheR: 0, total: 0, cost: 0, unknown: false });
    out.push({ date: day.date, models, sub });
  }
  return out;
});

/* Grand total over the visible range. */
const grand = computed(() => days.value.reduce((a, d) => {
  a.calls += d.sub.calls; a.prompt += d.sub.prompt; a.completion += d.sub.completion;
  a.cacheW += d.sub.cacheW; a.cacheR += d.sub.cacheR; a.total += d.sub.total;
  a.cost += d.sub.cost; a.unknown = a.unknown || d.sub.unknown;
  return a;
}, { calls: 0, prompt: 0, completion: 0, cacheW: 0, cacheR: 0, total: 0, cost: 0, unknown: false }));

/* Per-model rollup for the side panel, priced models first (by cost desc),
   unpriced after (by tokens desc). Bar width follows cost share, falling back
   to token share for models with no price entry. */
const modelRows = computed(() => {
  const by = new Map();
  for (const day of days.value) for (const m of day.models) {
    const b = by.get(m.uri) || { uri: m.uri, calls: 0, prompt: 0, completion: 0, cacheW: 0, cacheR: 0, total: 0 };
    b.calls += m.calls; b.prompt += m.prompt; b.completion += m.completion;
    b.cacheW += m.cacheW; b.cacheR += m.cacheR; b.total += m.total;
    by.set(m.uri, b);
  }
  const rows = [...by.values()].map(b => ({ ...b, ...costFor(b, data.value?.prices || {}) }));
  rows.sort((a, b) => {
    if (a.known !== b.known) return a.known ? -1 : 1;
    return a.known ? b.cost - a.cost : b.total - a.total;
  });
  const maxCost = Math.max(0, ...rows.filter(r => r.known).map(r => r.cost));
  const grandTotal = grand.value.total || 1;
  for (const r of rows) r.bar = r.known && maxCost ? (r.cost / maxCost) * 100 : (r.total / grandTotal) * 100;
  return rows;
});

/* The four summary cards. */
const cards = computed(() => ({
  cost: grand.value.cost,
  unknown: grand.value.unknown,
  unpriced: modelRows.value.filter(r => !r.known).length,
  tokens: grand.value.total,
  inn: grand.value.prompt,
  out: grand.value.completion,
  cache: grand.value.cacheW + grand.value.cacheR,
  calls: grand.value.calls,
  conversations: data.value?.conversations || 0,
  activeDays: days.value.length,
  since: days.value.length ? days.value[days.value.length - 1].date : null,
}));

onMounted(load);
</script>

<template>
  <div class="usage">
    <header class="up-head">
      <h1>Usage</h1>
      <span class="sub" v-if="data">{{ data.conversations }} conversations · scanned {{ data.scanned_at }}</span>
      <div class="spacer"></div>
      <div class="seg">
        <button :class="{ on: rangeDays === 7 }" @click="rangeDays = 7">7 days</button>
        <button :class="{ on: rangeDays === 30 }" @click="rangeDays = 30">30 days</button>
      </div>
      <button class="tbtn" title="Refresh" @click="load">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M23 4v6h-6M1 20v-6h6"/>
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
        </svg>
      </button>
    </header>

    <div v-if="loading && !data" class="state">Loading usage…</div>
    <div v-else-if="error" class="state">{{ error }}</div>
    <template v-else-if="data">
      <div class="cards">
        <div class="card">
          <div class="k">Total spent</div>
          <div class="v money">{{ money(cards.cost) }}</div>
          <div class="d" v-if="cards.unknown"><span class="warn">+ unknown</span> · {{ cards.unpriced }} model(s) unpriced</div>
          <div class="d" v-else>last {{ rangeDays }} days</div>
        </div>
        <div class="card">
          <div class="k">Total tokens</div>
          <div class="v">{{ compact(cards.tokens) }}</div>
          <div class="d">{{ compact(cards.inn) }} in · {{ compact(cards.out) }} out · {{ compact(cards.cache) }} cache</div>
        </div>
        <div class="card">
          <div class="k">API calls</div>
          <div class="v">{{ fmtNum(cards.calls) }}</div>
          <div class="d">across {{ cards.conversations }} conversations</div>
        </div>
        <div class="card">
          <div class="k">Active days</div>
          <div class="v">{{ cards.activeDays }}</div>
          <div class="d">{{ cards.since ? `since ${cards.since}` : "no activity in range" }}</div>
        </div>
      </div>

      <div v-if="!days.length" class="state">No LLM usage in the last {{ rangeDays }} days.</div>
      <div v-else class="cols">
        <div class="col-day">
          <div class="sec-title">By day</div>
          <div class="table-wrap">
            <table class="dt">
              <thead>
                <tr class="hdr">
                  <th>date</th><th>model</th><th>calls</th><th>in</th><th>out</th>
                  <th>cache</th><th>total</th><th>cost</th>
                </tr>
              </thead>
              <tbody>
                <template v-for="(d, di) in days" :key="d.date">
                  <tr v-for="(m, mi) in d.models" :key="m.uri" :class="{ 'day-start': di > 0 && mi === 0 }">
                    <td v-if="mi === 0" class="day-cell" :rowspan="d.models.length + 1">{{ d.date }}</td>
                    <td class="model">{{ m.uri }}</td>
                    <td>{{ fmtNum(m.calls) }}</td><td>{{ fmtNum(m.prompt) }}</td><td>{{ fmtNum(m.completion) }}</td>
                    <td>{{ fmtNum(m.cacheW + m.cacheR) }}</td><td>{{ fmtNum(m.total) }}</td>
                    <td :class="m.known ? 'money' : 'unknown'">{{ m.known ? money(m.cost) : "unknown" }}</td>
                  </tr>
                  <tr class="subtotal">
                    <td><span class="lbl">subtotal</span></td>
                    <td>{{ fmtNum(d.sub.calls) }}</td><td>{{ fmtNum(d.sub.prompt) }}</td><td>{{ fmtNum(d.sub.completion) }}</td>
                    <td>{{ fmtNum(d.sub.cacheW + d.sub.cacheR) }}</td><td>{{ fmtNum(d.sub.total) }}</td>
                    <td class="money">{{ money(d.sub.cost) }}<span v-if="d.sub.unknown" class="unknown"> + unknown</span></td>
                  </tr>
                  <tr v-if="di < days.length - 1" class="gap"><td colspan="8"></td></tr>
                </template>
                <tr class="grand">
                  <td>total</td><td class="txt">{{ modelRows.length }} model(s) · {{ days.length }} day(s)</td>
                  <td>{{ fmtNum(grand.calls) }}</td><td>{{ fmtNum(grand.prompt) }}</td><td>{{ fmtNum(grand.completion) }}</td>
                  <td>{{ fmtNum(grand.cacheW + grand.cacheR) }}</td><td>{{ fmtNum(grand.total) }}</td>
                  <td class="money">{{ money(grand.cost) }}<span v-if="grand.unknown" class="unknown"> + unknown</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="col-model">
          <div class="sec-title">By model</div>
          <div class="msum">
            <div v-for="r in modelRows" :key="r.uri" class="mrow">
              <div class="top">
                <span class="name">{{ r.uri }}</span>
                <span class="cost" :class="{ unknown: !r.known }">{{ r.known ? money(r.cost) : "unknown" }}</span>
              </div>
              <div class="bar"><i :class="{ amber: !r.known }" :style="{ width: r.bar + '%' }"></i></div>
              <div class="meta">
                <span>{{ fmtNum(r.calls) }} calls</span><span>{{ compact(r.prompt) }} in</span><span>{{ compact(r.completion) }} out</span>
                <span v-if="r.cacheW + r.cacheR">{{ compact(r.cacheW + r.cacheR) }} cache</span>
                <span v-if="!r.known">no price entry</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="foot">
        Costs are estimates from <a class="ext" href="https://token.app" @click.prevent="openPriceSource">token.app</a> — actual billing varies by provider (peak/off-peak rates, cache tiers, committed-use discounts) and is not reflected here.
      </div>
    </template>
  </div>
</template>

<style scoped>
.usage { height: 100%; overflow-y: auto; padding: 20px 28px 40px; }

/* ── header row: title + range filter + refresh ── */
.up-head { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
.up-head h1 { font: 700 15px var(--mono); letter-spacing: .5px; text-transform: uppercase; }
.up-head .sub { font: 400 10.5px var(--mono); color: var(--text-4); }
.up-head .spacer { flex: 1; }
.seg { display: flex; border: 1px solid var(--border); }
.seg button {
  background: none; border: none; cursor: pointer; padding: 5px 12px;
  font: 400 10.5px var(--mono); color: var(--text-3);
  border-right: 1px solid var(--border);
}
.seg button:last-child { border-right: none; }
.seg button:hover { background: var(--bg-hover); color: var(--text); }
.seg button.on { background: var(--brand); color: var(--on-brand); font-weight: 600; }
.tbtn {
  width: 26px; height: 26px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-4); border: 1px solid var(--border); background: none;
}
.tbtn:hover { color: var(--brand); background: var(--bg-hover); }
.tbtn svg { width: 13px; height: 13px; }

/* ── summary cards ── */
.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 22px; }
.card { border: 1px solid var(--border); background: var(--bg-panel); padding: 12px 14px; }
.card .k {
  font: 400 9.5px var(--mono); color: var(--text-4);
  text-transform: uppercase; letter-spacing: 1px; margin-bottom: 7px;
}
.card .v { font: 600 19px var(--mono); }
.card .v.money { color: var(--brand); }
.card .d { font: 400 10px var(--mono); color: var(--text-4); margin-top: 4px; }
.card .d .warn { color: var(--amber); }

/* ── two-column body: same 4-column grid as the cards, so By day sits under
      cards 1–3 and By model under card 4 ── */
.cols { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; align-items: start; }
.cols .col-day { grid-column: 1 / 4; }
.cols .col-model { grid-column: 4; }
.sec-title {
  font: 600 10px var(--mono); color: var(--text-3);
  text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 8px;
  display: flex; align-items: center; gap: 8px;
}
.sec-title::after { content: ""; flex: 1; height: 1px; background: var(--border); }

/* ── daily × model table ── */
.table-wrap { overflow-x: auto; }
table.dt { width: 100%; border-collapse: collapse; border: 1px solid var(--border); font: 400 11px var(--mono); }
.dt .hdr {
  background: var(--bg-panel); color: var(--text-4);
  font-size: 9.5px; text-transform: uppercase; letter-spacing: 1px;
  position: sticky; top: 0;
}
/* Numeric columns right-align so digits stack; date and model names sit left.
   Left-alignment goes through classes, not :nth-child — rows after a rowspan
   are shifted one cell, which would make nth-child hit a numeric column. */
.dt th, .dt td { padding: 6px 10px; text-align: right; white-space: nowrap; }
.dt th:first-child, .dt td:first-child { text-align: left; }
.dt th:nth-child(2) { text-align: left; }
.dt td.model, .dt td.txt { text-align: left; }
.dt thead th { border-bottom: 1px solid var(--border-soft); }
.dt tbody tr:hover { background: var(--bg-hover); }
.dt .day-cell { vertical-align: middle; color: var(--text); font-weight: 600; }
.dt .model { color: var(--text-2); }
.dt .money { color: var(--text); }
.dt .unknown { color: var(--amber); }
/* Rows inside one day carry no border — in border-collapse mode a row border
   would cut across the rowspan'd date cell. The subtotal line closes each
   group; a rule opens every day after the first. */
.dt tr.day-start td { border-top: 1px solid var(--border-soft); }
.dt tr.gap td { padding: 0; height: 18px; border: none; }
.dt tr.gap:hover td { background: none; }
.dt tr.subtotal td {
  background: var(--bg-raise); color: var(--text-2);
  font-weight: 600; border-bottom: 1px solid var(--border);
}
.dt tr.subtotal td .lbl { color: var(--text-4); font-weight: 400; }
.dt tr.grand td { background: var(--bg-raise); font-weight: 700; border-top: 2px solid var(--border-soft); }
.dt tr.grand td.money { color: var(--brand); }

/* ── model summary side panel ── */
.msum { border: 1px solid var(--border); background: var(--bg-panel); }
.mrow { padding: 10px 12px; border-bottom: 1px solid var(--border); }
.mrow:last-child { border-bottom: none; }
.mrow .top { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
.mrow .name { font: 500 11px var(--mono); color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mrow .cost { font: 600 11px var(--mono); color: var(--brand); flex-shrink: 0; margin-left: 8px; }
.mrow .bar { height: 3px; background: var(--bg-raise); margin-bottom: 5px; }
.mrow .bar i { display: block; height: 100%; background: var(--brand); }
.mrow .bar i.amber { background: var(--amber); }
.mrow .meta { display: flex; gap: 10px; font: 400 9.5px var(--mono); color: var(--text-4); }

.foot { margin-top: 18px; font: 400 10px var(--mono); color: var(--text-4); }
.foot .ext { color: var(--brand); text-decoration: none; cursor: pointer; }
.foot .ext:hover { text-decoration: underline; }
.state { padding: 40px 0; text-align: center; font: 400 11px var(--mono); color: var(--text-4); }

/* ── responsive: stack the columns, fold the cards, let the table scroll ── */
@media (max-width: 1100px) {
  .cols { grid-template-columns: 1fr; }
  .cols .col-day { grid-column: 1; }
  .cols .col-model { grid-column: 1; }
}
@media (max-width: 860px) {
  .cards { grid-template-columns: repeat(2, 1fr); }
}
</style>
