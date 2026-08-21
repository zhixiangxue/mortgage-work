<script setup>
/* Knowledge Graph pane — the FalkorDB face of the knowledge base: a lazy
   tree over this user's graph (lender → product → …) plus a node-detail
   split. One of two DATA tabs opened from the sidebar KB tree (the other
   is KbUnitsPane); no header, no in-pane navigation — the tab title
   already says which store this is, so the pane goes straight to the
   content. Read-only; scoping to the logged-in user is enforced in
   app.py — the bridge methods take no graph argument. */
import { ref, computed, watch, onMounted } from "vue";
import {
  store, loadKnowledge, loadKbBrowser, loadKbInfo, loadKbRoots,
  fetchKbChildren, fetchKbNode, isKbPlan,
} from "../store.js";
import KbUpgrade from "./KbUpgrade.vue";

/* ════════════════ plan gate ════════════════
   The tab stays reachable on the Free plan — the chip never lies — but
   the data is replaced by a bare guide card (KbUpgrade). */
const kbOn = computed(() => isKbPlan());

watch(kbOn, on => {
  if (on) { loadKnowledge(); loadKbBrowser(); }
});

/* ════════════════ store info ════════════════ */

const kb = computed(() => store.kbBrowser);
const fInfo = computed(() => (kb.value.info || {}).falkordb || null);
const ok = side => side && !side.error;

const kgError = computed(() => {
  if (ok(fInfo.value) && !kb.value.rootsError) return "";
  if (fInfo.value && fInfo.value.error) return fInfo.value.error;
  return kb.value.rootsError;
});

/* ════════════════ tree + detail ════════════════ */

/* The tree is component-local state: roots arrive from the store, every hop
   below is fetched on demand. Flattened into a visible-row list so the
   template needs no recursion. immediate: roots load once per session, so
   a (re)mounted pane must seed the tree from whatever the store already
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

/* ════════════════ refresh ════════════════
   The loading class is "spinning" — .spinner stays the status chip's ring. */
const spin = ref(false);

async function refresh() {
  if (spin.value) return;
  spin.value = true;
  loadKbInfo();
  await loadKbRoots();
  spin.value = false;
}

onMounted(() => {
  // Deferred one tick so the tab and this pane's skeleton paint before the
  // bridge fetches are issued — the loaders are boot-guarded, so running
  // them twice costs nothing.
  setTimeout(() => {
    loadKnowledge();   // sidebar KB tree shows live indexing counts
    // The data only exists on a KB plan — on Free the upgrade board renders
    // instead, and the watch above loads data the moment one unlocks.
    if (isKbPlan()) loadKbBrowser();
  }, 0);
});
</script>

<template>
  <div class="kb-pane">
    <KbUpgrade v-if="!kbOn" />
    <div v-else class="pane">
      <div v-if="kgError" class="fallback">
        <div class="fb-t">Knowledge Graph is unavailable</div>
        <div class="fb-m">{{ kgError }}. Try the refresh button, or sign out and back in if this persists.</div>
      </div>
      <template v-else>
        <div class="tbar">
          <span v-if="ok(fInfo)" class="tag">{{ Number(fInfo.nodes).toLocaleString() }} nodes · {{ Number(fInfo.edges).toLocaleString() }} edges</span>
          <span class="grow"></span>
          <span class="tag ro">read-only</span>
          <button class="refresh" :class="{ spinning: spin }" title="Refresh" @click="refresh">
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
</template>

<style scoped>
.kb-pane {
  flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden;
  background: var(--bg-editor);
  padding: 28px 36px 0; font: 13px var(--sans); color: var(--text);
}

.pane { flex: 1; min-height: 0; display: flex; flex-direction: column; }

/* ── toolbar bits ── */
.tbar { flex: none; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
        padding: 12px 2px; border-bottom: 1px solid var(--border); }
.tag { font: 11px var(--mono); padding: 2px 8px;
       background: var(--bg-raise); border: 1px solid var(--border); color: var(--text-3); }
.tag.ro { color: var(--text-4); border-style: dashed; }
.tbar .grow { flex: 1; }

/* Pane refresh: right after the read-only chip, spins while reloading */
.tbar .refresh { background: none; border: none; color: var(--text-4);
                 padding: 3px; cursor: pointer; line-height: 0; }
.tbar .refresh svg { width: 14px; height: 14px; display: block; }
.tbar .refresh:hover { color: var(--brand); }
.tbar .refresh.spinning svg { animation: sp .8s linear infinite; transform-origin: 50% 50%; }
@keyframes sp { to { transform: rotate(360deg); } }

/* ── degraded pane: friendly board instead of a dead tree ── */
.fallback { flex: 1; display: flex; flex-direction: column; align-items: center;
            justify-content: center; gap: 8px; padding: 40px; text-align: center; }
.fallback .fb-t { color: var(--text-2); font-size: 13.5px; font-weight: 500; }
.fallback .fb-m { color: var(--text-4); font-size: 12px; max-width: 420px; }

/* ── tree + detail split ── */
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
