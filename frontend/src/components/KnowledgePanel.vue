<script setup>
/* Knowledge Base panel — the DATA face of the knowledge base: what the
   raw stores actually hold — the Document Index (this user's Qdrant
   collection, a newest-first window over the latest units) and the
   Knowledge Graph (this user's FalkorDB graph, lazy tree + node detail).
   Read-only; scoping to the logged-in user is enforced in app.py — the
   bridge methods take no collection/graph argument.

   The PROCESS face (per-document indexing status) is a separate tab —
   IndexingPanel.vue — reached via the header button, which breathes
   while work is in flight but never disappears. */
import { ref, computed, watch, onMounted } from "vue";
import {
  store, openIndexing, openPlan, loadKnowledge,
  loadKbBrowser, loadKbInfo, loadKbPoints, loadKbRoots,
  fetchKbChildren, fetchKbNode, isKbPlan,
} from "../store.js";

/* ════════════════ plan gate ════════════════
   The panel stays reachable on the Free plan — the chip never lies — but
   the data dashboard is replaced by a bare guide card. The card carries no
   upgrade UI of its own: it just opens the Plan tab (openPlan), the single
   home for redemption codes, downgrades and, later, billing. */
const kbOn = computed(() => isKbPlan());

watch(kbOn, on => {
  if (on) { loadKnowledge(); loadKbBrowser(); }
});

/* ════════════════ header ════════════════ */

const kb = computed(() => store.kbBrowser);
const qInfo = computed(() => (kb.value.info || {}).qdrant || null);
const fInfo = computed(() => (kb.value.info || {}).falkordb || null);
const ok = side => side && !side.error;

const headerSum = computed(() => {
  const parts = [];
  if (ok(qInfo.value) && qInfo.value.points != null)
    parts.push(`${Number(qInfo.value.points).toLocaleString()} units`);
  if (ok(fInfo.value)) {
    if (fInfo.value.lenders != null) parts.push(`${fInfo.value.lenders} lenders`);
    if (fInfo.value.products != null) parts.push(`${fInfo.value.products} products`);
  }
  return parts.join(" · ");
});

/* Header door to the Indexing Status tab: ALWAYS present, but loudness
   follows the pipeline — a breathing dot + counts while work is in
   flight, a quiet label once everything has settled. Failed outranks
   processing for the dot color. */
const statusLive = computed(() =>
  (store.knowledge.processing || 0) + (store.knowledge.failed || 0) > 0);
const statusText = computed(() => {
  const p = store.knowledge.processing || 0, f = store.knowledge.failed || 0;
  const parts = [];
  if (p) parts.push(`${p} processing`);
  if (f) parts.push(`${f} failed`);
  return parts.join(" · ");
});

/* ════════════════ storage tabs ════════════════ */

const tab = ref("rag");  // "rag" | "kg" — same words as the status columns

const vectorChip = computed(() => {
  if (!ok(qInfo.value)) return "";
  const v = (qInfo.value.vectors || [])[0];
  return v ? `${v.size}-d · ${v.distance}` : "";
});

/* ════════════════ Document Index pane ════════════════ */

/* Three columns only: kind glyph (unit_type as icon — the raw word means
   nothing to an LO), document (file name big, doc id small underneath) and
   the unit text. The raw point id carries no meaning for a customer, so it
   stays out of the grid. */
const pl = p => p.payload || {};

/* Unit kind as a coloured icon — LOs don't read the raw payload word.
   Live data carries "text" / "table"; anything else keeps its own label
   in the tooltip and falls back to the dot. */
function unitIcon(t) {
  if (t === "text") return "par";
  if (t === "table") return "tbl";
  return t ? "" : "none";
}
function unitTip(t) {
  return t || "no unit_type in payload";
}

/* Inline expansion — click the text cell to unfold the unit's full content
   right in the row. One open at a time keeps the grid readable. A modal
   yanked you out of context for what is really just a peek, so it's gone.

   Clicks only ever EXPAND: once a row is open the cell turns into plain
   selectable content, so dragging to copy text can never collapse it by
   accident. Folding happens via the minimize button on the open pane, or
   implicitly by clicking another row (which swaps the open unit). */
const expanded = ref(null);  // id of the unfolded point, null = all folded
function toggleExpand(p) {
  expanded.value = expanded.value === p.id ? null : p.id;
}

/* Infinite-scroll machinery survives but idles: the backend answers the
   whole newest-first window in one shot (next=null), so the first fetch
   flips pointsEnd and no further page is ever requested. */
const gridWrap = ref(null);
function onGridScroll() {
  const el = gridWrap.value;
  if (el && el.scrollTop + el.clientHeight >= el.scrollHeight - 120) loadKbPoints();
}

const moreLabel = computed(() => {
  if (!kb.value.points.length) return "";
  return `latest ${kb.value.points.length} units · newest first`;
});

/* Pane degraded to a friendly board: not configured / unreachable / empty
   session. Only kills its own pane. */
const ragError = computed(() => {
  if (ok(qInfo.value)) return "";
  if (qInfo.value && qInfo.value.error) return qInfo.value.error;
  return kb.value.pointsError;
});

/* ════════════════ Knowledge Graph pane ════════════════ */

const kgError = computed(() => {
  if (ok(fInfo.value) && !kb.value.rootsError) return "";
  if (fInfo.value && fInfo.value.error) return fInfo.value.error;
  return kb.value.rootsError;
});

/* The tree is component-local state: roots arrive from the store, every hop
   below is fetched on demand. Flattened into a visible-row list so the
   template needs no recursion. immediate: roots load once per session, so
   a (re)mounted panel must seed the tree from whatever the store already
   holds — waiting for a change would leave it empty until someone hits
   refresh. */
const tree = ref([]);
const selected = ref(null);
const detail = ref(null);        // full node props, or { error }
const detailLoading = ref(false);

watch(() => kb.value.roots, roots => {
  tree.value = (roots || []).map(r =>
    ({ ...r, open: false, loaded: false, loading: false, kids: [] }));
  selected.value = null;
  detail.value = null;
}, { immediate: true });

const flatTree = computed(() => {
  const out = [];
  (function walk(nodes, depth) {
    for (const n of nodes) {
      out.push({ n, depth });
      if (n.open) walk(n.kids, depth + 1);
    }
  })(tree.value, 0);
  return out;
});

async function toggle(n) {
  if (n.leaf) return;
  if (n.open) { n.open = false; return; }
  n.open = true;
  if (n.loaded) return;
  n.loading = true;
  const res = await fetchKbChildren(n.id, n.type);
  n.loading = false;
  if (!res || res.error) {
    n.kidsError = (res && res.error) || "bridge error";
    return;
  }
  n.kidsError = "";
  n.kids = (res.children || []).map(c =>
    ({ ...c, open: false, loaded: false, loading: false, kids: [] }));
  n.loaded = true;
}

async function select(n) {
  selected.value = n;
  detail.value = null;
  detailLoading.value = true;
  const res = await fetchKbNode(n.id, n.type);
  detailLoading.value = false;
  if (!res || res.error) {
    detail.value = { error: (res && res.error) || "bridge error" };
    return;
  }
  detail.value = res.node;
}

function propRows(node) {
  return Object.entries(node.props || {}).map(([k, v]) => ({
    k, v: typeof v === "string" ? v : JSON.stringify(v),
  }));
}

/* ════════════════ refresh buttons ════════════════
   Each button lives in its own pane toolbar and reloads only that pane.
   The loading class is "spinning" — .spinner stays the status chip's ring. */
const spinRag = ref(false), spinKg = ref(false);

async function refreshRag() {
  if (spinRag.value) return;
  spinRag.value = true;
  loadKbInfo();
  await loadKbPoints(true);
  spinRag.value = false;
}

async function refreshKg() {
  if (spinKg.value) return;
  spinKg.value = true;
  loadKbInfo();
  await loadKbRoots();
  spinKg.value = false;
}

onMounted(() => {
  loadKnowledge();   // header door needs fresh processing/failed counts
  // The data dashboard only exists on a KB plan — on Free the upgrade board
  // renders instead, and the watch above loads data the moment one unlocks.
  if (isKbPlan()) loadKbBrowser();
});
</script>

<template>
  <div id="knowledge-panel">
    <!-- ── header ──
         On Free the panel is a bare upgrade board — not even the title:
         nothing competes with the card for attention. -->
    <div v-if="kbOn" class="head">
      <h1>Knowledge Base</h1>
      <span class="sum">{{ headerSum }}</span>
      <!-- Door to the Indexing Status tab: always here (progress must be
           inspectable any time), but loud only while the pipeline works —
           breathing dot + live counts, quiet label once settled. -->
      <button class="status-btn" @click="openIndexing()">
        <span v-if="statusLive" class="pulse" :class="{ bad: store.knowledge.failed > 0 }"></span>
        <span>{{ statusLive ? statusText : "Indexing status" }}</span>
        <!-- SVG arrow, not the "→" glyph — glyphs render uneven next to UI text -->
        <svg class="go" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="M13 6l6 6-6 6"/></svg>
      </button>
    </div>
    <div v-if="kbOn" class="sub">
      Everything the assistant has learned from your product library, as stored in the two databases.
    </div>

    <!-- ════════════ FREE guide card ════════════
         Guidance only — the Upgrade tab owns every redemption/billing
         control, so this card never duplicates that UI. -->
    <div v-if="!kbOn" class="upgrade">
      <div class="up-card">
        <div class="up-t">Personal knowledge base is a Pro feature</div>
        <div class="up-m">
          On the Free plan your product library stays local — documents are
          never sent to the databases, and the assistant can't answer from
          them. Shared knowledge bases mounted in Settings still work.
        </div>
        <div class="up-perks">
          <div>· Documents indexed into the Document Index</div>
          <div>· Knowledge Graph built from your product library</div>
          <div>· Assistant answers grounded in your own products</div>
        </div>
        <button class="btn-sm primary up-btn" @click="openPlan()">Upgrade</button>
      </div>
    </div>

    <!-- ════════════ DATA dashboard ════════════ -->
    <div v-else class="data-view">
      <div class="stabs">
        <div class="stab" :class="{ on: tab === 'rag' }" @click="tab = 'rag'">
          Document Index<span v-if="ok(qInfo) && qInfo.points != null" class="n">{{ Number(qInfo.points).toLocaleString() }} units</span>
        </div>
        <div class="stab" :class="{ on: tab === 'kg' }" @click="tab = 'kg'">
          Knowledge Graph<span v-if="ok(fInfo) && fInfo.products != null" class="n">{{ fInfo.products }} products</span>
        </div>
      </div>

      <!-- ── Document Index: flat points browser (qdrant viewer shape) ── -->
      <div v-show="tab === 'rag'" class="pane">
        <div v-if="ragError" class="fallback">
          <div class="fb-t">Document Index is unavailable</div>
          <div class="fb-m">{{ ragError }}. Try the refresh button, or sign out and back in if this persists.</div>
        </div>
        <template v-else>
          <div class="tbar">
            <span v-if="vectorChip" class="tag">{{ vectorChip }}</span>
            <span class="grow"></span>
            <span class="tag ro">read-only</span>
            <button class="refresh" :class="{ spinning: spinRag }" title="Refresh" @click="refreshRag">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            </button>
          </div>
          <!-- First paint: the order_by window takes a moment on the server,
               so an empty grid gets a centred spinner instead of the old
               quiet "loading…" caption nobody noticed. -->
          <div v-if="kb.loadingPoints && !kb.points.length" class="pane-load">
            <div class="fb-spin"></div>
            <div class="pl-label">Loading document index…</div>
          </div>
          <div v-else ref="gridWrap" class="grid-wrap" @scroll="onGridScroll">
            <table class="grid">
              <thead><tr>
                <th style="width: 38px"></th>
                <th style="width: 27%">document</th>
                <th>text</th>
              </tr></thead>
              <tbody>
                <tr v-for="p in kb.points" :key="p.id">
                  <!-- Kind glyph: the raw unit_type word means nothing to an
                       LO — colour + shape carry it, tooltip keeps the word -->
                  <td class="kind" :title="unitTip(pl(p).unit_type)">
                    <svg v-if="unitIcon(pl(p).unit_type) === 'par'" class="uicon par" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="21" y1="6" x2="3" y2="6"/><line x1="15" y1="12" x2="3" y2="12"/><line x1="17" y1="18" x2="3" y2="18"/></svg>
                    <svg v-else-if="unitIcon(pl(p).unit_type) === 'tbl'" class="uicon tbl" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M12 3v18"/></svg>
                    <span v-else class="uicon none">&middot;</span>
                  </td>
                  <td class="doc-cell">
                    <div class="fname">{{ pl(p).file_name }}</div>
                    <div class="fdoc">{{ pl(p).doc_id }}</div>
                  </td>
                  <!-- While open the cell stops being a toggle: text must stay
                       selectable for copying. The "click" affordance (cursor +
                       hover tint) follows the folded state only. -->
                  <td class="txt" :class="{ open: expanded === p.id, click: expanded !== p.id }"
                      @click="expanded !== p.id && toggleExpand(p)">
                    <!-- The clamp lives on an inner div: putting display:-webkit-box
                         on the td itself overrides table-cell and the cut line
                         lands mid-glyph. -->
                    <div v-if="pl(p).text && expanded !== p.id" class="clamp">{{ pl(p).text }}</div>
                    <span v-else-if="!pl(p).text" class="null">null</span>
                    <!-- Peek: full unit content unfolded in place; the only fold
                         control is the minimize button — clicks inside never collapse -->
                    <div v-if="pl(p).text && expanded === p.id" class="full-wrap">
                      <button class="fold" title="Fold" @click.stop="toggleExpand(p)">
                        <!-- Minimize (inward arrows) — the expand/shrink pair's
                             shrink half, reads as "fold this back down" -->
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
                      </button>
                      <div class="full">{{ pl(p).text }}</div>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            <div class="more">{{ moreLabel }}</div>
          </div>
        </template>
      </div>

      <!-- ── Knowledge Graph: lazy tree + node detail (falkordb viewer shape) ── -->
      <div v-show="tab === 'kg'" class="pane">
        <div v-if="kgError" class="fallback">
          <div class="fb-t">Knowledge Graph is unavailable</div>
          <div class="fb-m">{{ kgError }}. Try the refresh button, or sign out and back in if this persists.</div>
        </div>
        <template v-else>
          <div class="tbar">
            <span v-if="ok(fInfo)" class="tag">{{ Number(fInfo.nodes).toLocaleString() }} nodes · {{ Number(fInfo.edges).toLocaleString() }} edges</span>
            <span class="grow"></span>
            <span class="tag ro">read-only</span>
            <button class="refresh" :class="{ spinning: spinKg }" title="Refresh" @click="refreshKg">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            </button>
          </div>
          <div class="kg-split">
            <div class="kg-tree">
              <div v-if="kb.rootsLoading && !tree.length" class="loading">loading lenders…</div>
              <div v-else-if="!tree.length" class="loading">No graph yet — products indexed from the library land here.</div>
              <template v-for="{ n, depth } in flatTree" :key="n.type + ':' + n.id">
                <div class="trow" :class="{ sel: selected === n }"
                     :style="{ paddingLeft: 8 + depth * 20 + 'px' }" @click="select(n)">
                  <span v-if="!n.leaf" class="caret" :class="{ open: n.open }"
                        @click.stop="toggle(n)">▶</span>
                  <span v-else class="caret none">▶</span>
                  <span class="tlabel" :class="n.type">{{ n.type }}</span>
                  <span class="tname">{{ n.name }}</span>
                  <span v-if="n.count != null" class="tcount">{{ n.count }}</span>
                </div>
                <div v-if="n.open && n.loading" class="loading"
                     :style="{ paddingLeft: 28 + depth * 20 + 'px' }">loading…</div>
                <div v-else-if="n.open && n.kidsError" class="loading"
                     :style="{ paddingLeft: 28 + depth * 20 + 'px' }">{{ n.kidsError }}</div>
              </template>
            </div>
            <div class="kg-detail">
              <div v-if="detailLoading" class="dempty">loading…</div>
              <div v-else-if="!detail" class="dempty">Select a node to inspect its properties.</div>
              <div v-else-if="detail.error" class="dempty">{{ detail.error }}</div>
              <template v-else>
                <div class="dh">
                  <span class="tlabel" :class="detail.type">{{ detail.type }}</span>
                  <span class="nm">{{ detail.name }}</span>
                </div>
                <div class="dsub">{{ detail.id }}</div>
                <table class="ptable">
                  <tr v-for="r in propRows(detail)" :key="r.k">
                    <td class="k">{{ r.k }}</td><td class="v">{{ r.v }}</td>
                  </tr>
                </table>
              </template>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
#knowledge-panel {
  flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden;
  background: var(--bg-editor);
  padding: 28px 36px 0; font: 13px var(--sans); color: var(--text);
}

/* ── header ─────────────────────────────────────────── */
.head { display: flex; align-items: baseline; gap: 14px; }
.head h1 { font-size: 17px; font-weight: 600; letter-spacing: .3px; }
.head .sum { color: var(--text-3); font-size: 12px; }
.sub { color: var(--text-4); font-size: 12px; margin: 4px 0 16px; }

/* Header door to the Indexing Status tab — always present; the breathing
   dot appears only while work is in flight (presence, not alarm). */
.status-btn {
  margin-left: auto; align-self: center; display: inline-flex; align-items: center;
  gap: 7px; background: var(--bg-raise); border: 1px solid var(--border);
  color: var(--text-3); font-size: 12px; padding: 4px 12px;
  cursor: pointer; white-space: nowrap;
}
.status-btn:hover { border-color: var(--border-soft); color: var(--text); }
.status-btn .go { width: 12px; height: 12px; color: var(--text-4); flex: none; }
.pulse { width: 7px; height: 7px; border-radius: 50%; background: var(--amber);
         animation: breathe 2.4s ease-in-out infinite; }
.pulse.bad { background: var(--red); }
@keyframes breathe { 0%, 100% { opacity: .35; transform: scale(.8); }
                     50% { opacity: 1; transform: scale(1); } }

/* Data dashboard fills the panel — the status table is its own tab now */
.data-view { flex: 1; min-height: 0; display: flex; flex-direction: column; }

/* ── Free upgrade board: the whole panel is one quiet card, vertically
      centred so nothing competes with it ── */
.upgrade { flex: 1; min-height: 0; overflow-y: auto; display: flex;
           align-items: center; justify-content: center; padding: 24px 20px; }
.up-card { width: 100%; max-width: 520px; background: var(--bg-panel);
           border: 1px solid var(--border); padding: 26px 30px; }
.up-t { font-size: 14.5px; font-weight: 600; margin-bottom: 10px; }
.up-m { color: var(--text-4); font-size: 12px; line-height: 1.65; }
.up-perks { margin: 16px 0 20px; display: flex; flex-direction: column; gap: 6px;
            color: var(--text-2); font-size: 12px; }
.up-btn { align-self: flex-start; }

/* ── storage tabs — the two faces of one knowledge base, same words as the
      status columns ── */
.stabs { display: flex; gap: 22px; border-bottom: 1px solid var(--border); flex: none; }
.stab { padding: 8px 2px 10px; font-size: 13px; color: var(--text-3); cursor: pointer;
        border-bottom: 2px solid transparent; margin-bottom: -1px; }
.stab:hover { color: var(--text-2); }
.stab.on { color: var(--text); border-bottom-color: var(--brand); font-weight: 500; }
.stab .n { color: var(--text-4); font-size: 11px; margin-left: 5px; }

.pane { flex: 1; min-height: 0; display: flex; flex-direction: column; }

/* ── shared toolbar bits (.tag — .chip is the status vocabulary below) ── */
.tbar { flex: none; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
        padding: 12px 2px; border-bottom: 1px solid var(--border); }
.tag { font: 11px var(--mono); padding: 2px 8px;
       background: var(--bg-raise); border: 1px solid var(--border); color: var(--text-3); }
.tag.ro { color: var(--text-4); border-style: dashed; }
.tbar .grow { flex: 1; }

/* Pane refresh: right after the read-only chip, spins while reloading.
   The loading class is "spinning" — .spinner is the status chip's ring. */
.tbar .refresh { background: none; border: none; color: var(--text-4);
                 padding: 3px; cursor: pointer; line-height: 0; }
.tbar .refresh svg { width: 14px; height: 14px; display: block; }
.tbar .refresh:hover { color: var(--brand); }
.tbar .refresh.spinning svg { animation: sp .8s linear infinite; transform-origin: 50% 50%; }
@keyframes sp { to { transform: rotate(360deg); } }

/* ── degraded pane: friendly board instead of a dead table ── */
.fallback { flex: 1; display: flex; flex-direction: column; align-items: center;
            justify-content: center; gap: 8px; padding: 40px; text-align: center; }
.fallback .fb-t { color: var(--text-2); font-size: 13.5px; font-weight: 500; }
.fallback .fb-m { color: var(--text-4); font-size: 12px; max-width: 420px; }

/* ── Document Index pane ── */
/* First-paint spinner — replaces the old easy-to-miss "loading…" caption.
   Same ring idiom as the app-wide .fb-spin (whitelisted circle in the
   global square-corner reset). */
.pane-load { flex: 1; display: flex; flex-direction: column; align-items: center;
             justify-content: center; gap: 12px; padding: 60px 0; }
.pane-load .fb-spin { width: 20px; height: 20px; border-radius: 50%;
                      border: 2px solid var(--border); border-top-color: var(--brand);
                      animation: fb-rot .7s linear infinite; }
.pane-load .pl-label { color: var(--text-4); font-size: 12px; }
@keyframes fb-rot { to { transform: rotate(360deg); } }

/* Vertical scroll only — the fixed layout forces every column into the
   pane width, so nothing ever scrolls sideways. */
.grid-wrap { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; margin: 0 -2px; }
table.grid { width: 100%; border-collapse: collapse; table-layout: fixed; }
.grid th { position: sticky; top: 0; z-index: 1; background: var(--bg-editor);
           text-align: left; font: 500 11px var(--mono); color: var(--text-4);
           letter-spacing: .4px; padding: 8px 10px; border-bottom: 1px solid var(--border); }
.grid td { padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: top;
           font-size: 12px; color: var(--text-2); overflow: hidden; }
/* Kind icon column — narrow, glyph centred; colours follow the KG tree
   badge language (blue text, amber table) */
.grid td.kind { padding: 8px 0 8px 10px; text-align: center; }
.grid .uicon { width: 14px; height: 14px; display: inline-block; vertical-align: middle; }
.grid .uicon.par { color: var(--blue); }
.grid .uicon.tbl { color: var(--amber); }
.grid .uicon.none { color: var(--text-4); font-size: 15px; line-height: 14px; }
/* Unit text: two lines as a teaser — the full value unfolds in place when
   the cell is clicked. line-clamp on the inner block; the explicit
   max-height is a second wall so WKWebView can never leak a half-line
   underneath. */
.grid td.txt { padding: 8px 10px; }
.grid td.txt .clamp { color: var(--text); line-height: 1.45;
                      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
                      overflow: hidden; word-break: break-word; max-height: 2.9em; }
/* Peek pane: raw unit content, brand accent on the left, scrolls on its own
   when a unit runs long. The minimize button sits top-right of the wrapper —
   always visible while open, quiet until hovered. */
.grid td.txt.open { background: var(--bg-hover); }
.grid td.txt .full-wrap { position: relative; }
/* Offset from the right edge so the button never sits on .full's own
   scrollbar when a long unit overflows the 360px cap. */
.grid td.txt .fold { position: absolute; top: 3px; right: 16px; z-index: 1;
                     background: var(--bg-raise); border: 1px solid var(--border);
                     color: var(--text-4); padding: 3px; line-height: 0; cursor: pointer; }
.grid td.txt .fold svg { width: 11px; height: 11px; display: block; }
.grid td.txt .fold:hover { color: var(--brand); border-color: var(--border-soft); }
.grid td.txt .full { padding: 10px 42px 10px 12px; max-height: 360px; overflow-y: auto;
                     border-left: 2px solid var(--brand); background: var(--bg);
                     font-size: 12px; line-height: 1.7; color: var(--text-2);
                     white-space: pre-wrap; word-break: break-word; }
/* Document cell: file name first, doc id as a quiet second line */
.grid td.doc-cell .fname { font-size: 12px; color: var(--text);
                           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.grid td.doc-cell .fdoc { font: 10.5px var(--mono); color: var(--text-4); margin-top: 2px;
                          white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.grid td.click { cursor: pointer; }
/* Only the text column is clickable — it alone gets the hover feedback.
   .clamp (and .null) pin their own colors, so the brand color has to be
   re-asserted on them directly. */
.grid td.txt.click:hover { color: var(--brand); }
.grid td.txt.click:hover .clamp, .grid td.txt.click:hover .null { color: var(--brand); }
.grid .null { color: var(--text-4); font-family: var(--mono); font-size: 11px; }
.more { padding: 12px 10px 18px; color: var(--text-4); font-size: 12px; text-align: center; }

/* ── Knowledge Graph pane: tree + detail split ── */
.kg-split { flex: 1; min-height: 0; display: flex; }
.kg-tree { flex: 1.2; min-width: 0; overflow: auto; padding: 10px 6px 24px 0;
           border-right: 1px solid var(--border); }
.kg-detail { flex: 1; min-width: 280px; overflow: auto; padding: 14px 0 24px 18px; }

.trow { display: flex; align-items: center; gap: 6px; padding: 4px 8px;
        cursor: pointer; white-space: nowrap; user-select: none; }
.trow:hover { background: var(--bg-hover); }
/* Selected node: a light brand-green wash — clearly visible but quiet */
.trow.sel { background: rgba(60, 215, 66, .10); }
.caret { flex: none; width: 14px; height: 14px; display: inline-flex; align-items: center;
         justify-content: center; color: var(--text-4); font-size: 10px;
         transition: transform .12s ease; }
.caret.open { transform: rotate(90deg); }
.caret.none { visibility: hidden; }
.tlabel { font: 700 8.5px var(--mono); letter-spacing: .8px; text-transform: uppercase;
          padding: 1px 5px; flex: none; }
.tlabel.Lender      { background: var(--tint-green); color: var(--brand); }
.tlabel.Product     { background: var(--tint-blue); color: var(--blue); }
.tlabel.Requirement { background: #1d1a10; color: var(--amber); }
.tlabel.Group       { background: var(--bg-raise); color: var(--text-3); }
.tlabel.Condition   { background: var(--bg-raise); color: var(--text-2); }
.tlabel.Field       { background: transparent; border: 1px solid var(--border); color: var(--text-4); }
.tname { font-size: 12.5px; color: var(--text); overflow: hidden; text-overflow: ellipsis; }
.tcount { font-size: 11px; color: var(--text-4); }
.loading { color: var(--text-4); font-size: 11px; padding: 3px 8px; }

.kg-detail .dh { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.kg-detail .dh .nm { font-size: 15px; font-weight: 600; }
.kg-detail .dsub { color: var(--text-4); font-size: 12px; margin-bottom: 14px; }
.ptable { width: 100%; border-collapse: collapse; }
.ptable td { padding: 6px 8px; border-bottom: 1px solid var(--border); font-size: 12px; vertical-align: top; }
.ptable td.k { font: 11px var(--mono); color: var(--text-4); width: 118px; white-space: nowrap; }
.ptable td.v { color: var(--text-2); word-break: break-word; }
.dempty { color: var(--text-4); font-size: 12.5px; padding-top: 30px; }
</style>
