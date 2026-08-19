<script setup>
/* Knowledge Base panel — the DATA face of the knowledge base: what the
   raw stores actually hold — the Document Index (this user's Qdrant
   collection, flat cursor-paged points) and the Knowledge Graph (this
   user's FalkorDB graph, lazy tree + node detail). Read-only; scoping to
   the logged-in user is enforced in app.py — the bridge methods take no
   collection/graph argument.

   The PROCESS face (per-document indexing status) is a separate tab —
   IndexingPanel.vue — reached via the header button, which breathes
   while work is in flight but never disappears. */
import { ref, computed, watch, onMounted } from "vue";
import {
  store, openIndexing, loadKnowledge,
  loadKbBrowser, loadKbInfo, loadKbPoints, loadKbRoots,
  fetchKbChildren, fetchKbNode,
} from "../store.js";

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

/* Three columns only: document (file name big, doc id small underneath),
   unit_type and the unit text. The raw point id carries no meaning for a
   customer, so it stays out of the grid. */
const pl = p => p.payload || {};

function cellVal(p, col) {
  const v = pl(p)[col];
  if (v == null) return "";
  return typeof v === "string" ? v : JSON.stringify(v);
}

/* Full-value modal — click any cell */
const modal = ref(null);  // { title, value }
function openCell(p, col) {
  modal.value = { title: `payload · ${col}`, value: cellVal(p, col) };
}
function openDoc(p) {
  // The document cell holds two values — show both in one modal.
  const d = pl(p);
  modal.value = { title: "document",
                  value: [d.file_name, d.doc_id].filter(Boolean).join("\n") };
}

/* Infinite scroll: near the bottom, pull the next cursor page */
const gridWrap = ref(null);
function onGridScroll() {
  const el = gridWrap.value;
  if (el && el.scrollTop + el.clientHeight >= el.scrollHeight - 120) loadKbPoints();
}

const moreLabel = computed(() => {
  if (kb.value.loadingPoints) return "loading more…";
  if (!kb.value.points.length) return "";
  if (kb.value.pointsEnd) return `end of list · ${kb.value.points.length} units shown`;
  return `${kb.value.points.length} units shown · scroll for more`;
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
   template needs no recursion. */
const tree = ref([]);
const selected = ref(null);
const detail = ref(null);        // full node props, or { error }
const detailLoading = ref(false);

watch(() => kb.value.roots, roots => {
  tree.value = (roots || []).map(r =>
    ({ ...r, open: false, loaded: false, loading: false, kids: [] }));
  selected.value = null;
  detail.value = null;
});

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
  loadKbBrowser();   // data dashboard: info + first points page + roots
});
</script>

<template>
  <div id="knowledge-panel">
    <!-- ── header ── -->
    <div class="head">
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
    <div class="sub">
      Everything the assistant has learned from your product library, as stored in the two databases.
    </div>

    <!-- ════════════ DATA dashboard ════════════ -->
    <div class="data-view">
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
          <div ref="gridWrap" class="grid-wrap" @scroll="onGridScroll">
            <table class="grid">
              <thead><tr>
                <th style="width: 27%">document</th>
                <th style="width: 88px">unit_type</th>
                <th>text</th>
              </tr></thead>
              <tbody>
                <tr v-for="p in kb.points" :key="p.id">
                  <td class="click doc-cell" @click="openDoc(p)">
                    <div class="fname">{{ pl(p).file_name }}</div>
                    <div class="fdoc">{{ pl(p).doc_id }}</div>
                  </td>
                  <td class="click mono" @click="openCell(p, 'unit_type')">
                    <span v-if="pl(p).unit_type">{{ pl(p).unit_type }}</span>
                    <span v-else class="null">null</span>
                  </td>
                  <td class="click txt" @click="openCell(p, 'text')">
                    <!-- The clamp lives on an inner div: putting display:-webkit-box
                         on the td itself overrides table-cell and the cut line
                         lands mid-glyph. -->
                    <div v-if="pl(p).text" class="clamp">{{ pl(p).text }}</div>
                    <span v-else class="null">null</span>
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
            <span class="tag">Lender → Product → Requirement → Group → Condition → Field</span>
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

    <!-- full-value modal (click any points-grid cell) -->
    <div v-if="modal" class="modal" @click.self="modal = null">
      <div class="card">
        <div class="mh"><span>{{ modal.title }}</span><span class="x" @click="modal = null">✕ close</span></div>
        <pre>{{ modal.value }}</pre>
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
/* Vertical scroll only — the fixed layout forces every column into the
   pane width, so nothing ever scrolls sideways. */
.grid-wrap { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; margin: 0 -2px; }
table.grid { width: 100%; border-collapse: collapse; table-layout: fixed; }
.grid th { position: sticky; top: 0; z-index: 1; background: var(--bg-editor);
           text-align: left; font: 500 11px var(--mono); color: var(--text-4);
           letter-spacing: .4px; padding: 8px 10px; border-bottom: 1px solid var(--border); }
.grid td { padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: top;
           font-size: 12px; color: var(--text-2); overflow: hidden; }
.grid td.mono { font-family: var(--mono); font-size: 11px; color: var(--text-3);
                white-space: nowrap; text-overflow: ellipsis; }
/* Unit text: two lines as a teaser — the full value lives in the modal.
   line-clamp on the inner block; the explicit max-height is a second wall
   so WKWebView can never leak a half-line underneath. */
.grid td.txt { padding: 8px 10px; }
.grid td.txt .clamp { color: var(--text); line-height: 1.45;
                      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
                      overflow: hidden; word-break: break-word; max-height: 2.9em; }
/* Document cell: file name first, doc id as a quiet second line */
.grid td.doc-cell .fname { font-size: 12px; color: var(--text);
                           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.grid td.doc-cell .fdoc { font: 10.5px var(--mono); color: var(--text-4); margin-top: 2px;
                          white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.grid td.click { cursor: pointer; }
.grid td.click:hover { color: var(--brand); }
.grid td.doc-cell.click:hover .fname { color: var(--brand); }
.grid tr:hover td { background: var(--bg-hover); }
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

/* ── full-value modal (click any grid cell) ── */
.modal { position: fixed; inset: 0; background: rgba(0,0,0,.65);
         display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal .card { width: min(680px, 90vw); max-height: 76vh; display: flex; flex-direction: column;
               background: var(--bg-panel); border: 1px solid var(--border-soft); }
.modal .mh { display: flex; align-items: center; padding: 12px 16px;
             border-bottom: 1px solid var(--border); font: 600 12px var(--mono); color: var(--text-2); }
.modal .mh .x { margin-left: auto; color: var(--text-4); cursor: pointer; font-family: var(--sans); }
.modal .mh .x:hover { color: var(--text); }
.modal pre { margin: 0; padding: 16px; overflow: auto; font: 12px/1.6 var(--mono);
             color: var(--text-2); white-space: pre-wrap; word-break: break-word; }
</style>
