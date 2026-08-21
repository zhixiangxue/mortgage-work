<script setup>
/* Document Index pane — the Qdrant face of the knowledge base: a
   newest-first window over the latest units in this user's collection.
   One of two DATA tabs opened from the sidebar KB tree (the other is
   KbGraphPane); no header, no in-pane navigation — the tab title already
   says which store this is, so the pane goes straight to the content.
   Read-only; scoping to the logged-in user is enforced in app.py — the
   bridge methods take no collection argument. */
import { ref, computed, watch, onMounted } from "vue";
import {
  store, loadKnowledge, loadKbBrowser, loadKbInfo, loadKbPoints, isKbPlan,
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
const qInfo = computed(() => (kb.value.info || {}).qdrant || null);
const ok = side => side && !side.error;

const vectorChip = computed(() => {
  if (!ok(qInfo.value)) return "";
  const v = (qInfo.value.vectors || [])[0];
  return v ? `${v.size}-d · ${v.distance}` : "";
});

/* ════════════════ grid ════════════════ */

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

/* Infinite scroll: pages of 100 from the newest-first window — the grid
   never paints the whole window at once (a 500-row replace used to freeze
   the pane). loadKbPoints is in-flight-guarded, so fast scroll events can
   pile up on the same page request without double-fetching. */
const gridWrap = ref(null);
function onGridScroll() {
  const el = gridWrap.value;
  if (el && el.scrollTop + el.clientHeight >= el.scrollHeight - 120) loadKbPoints();
}

const moreLabel = computed(() => {
  if (!kb.value.points.length) return "";
  return kb.value.pointsEnd
    ? `latest ${kb.value.points.length} units · newest first`
    : `loaded ${kb.value.points.length} units · newest first`;
});

/* Pane degraded to a friendly board: not configured / unreachable / empty
   session. Only kills its own pane. */
const ragError = computed(() => {
  if (ok(qInfo.value)) return "";
  if (qInfo.value && qInfo.value.error) return qInfo.value.error;
  return kb.value.pointsError;
});

/* ════════════════ refresh ════════════════
   The loading class is "spinning" — .spinner stays the status chip's ring. */
const spin = ref(false);

async function refresh() {
  if (spin.value) return;
  spin.value = true;
  loadKbInfo();
  await loadKbPoints(true);
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
      <div v-if="ragError" class="fallback">
        <div class="fb-t">Document Index is unavailable</div>
        <div class="fb-m">{{ ragError }}. Try the refresh button, or sign out and back in if this persists.</div>
      </div>
      <template v-else>
        <div class="tbar">
          <span v-if="vectorChip" class="tag">{{ vectorChip }}</span>
          <span class="grow"></span>
          <span class="tag ro">read-only</span>
          <button class="refresh" :class="{ spinning: spin }" title="Refresh" @click="refresh">
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
          <div class="more">
            <!-- Next page on its way: quiet ring in the footer instead of
                 a dead caption; the settled label names the window -->
            <template v-if="kb.loadingPoints && kb.points.length">
              <span class="more-spin"></span> loading more…
            </template>
            <template v-else>{{ moreLabel }}</template>
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

/* ── degraded pane: friendly board instead of a dead table ── */
.fallback { flex: 1; display: flex; flex-direction: column; align-items: center;
            justify-content: center; gap: 8px; padding: 40px; text-align: center; }
.fallback .fb-t { color: var(--text-2); font-size: 13.5px; font-weight: 500; }
.fallback .fb-m { color: var(--text-4); font-size: 12px; max-width: 420px; }

/* First-paint spinner — same ring idiom as the app-wide .fb-spin
   (whitelisted circle in the global square-corner reset). */
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
                      display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2;
                      -webkit-box-orient: vertical;
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
/* Footer spinner while the next page is in flight — whitelisted circle
   (.more-spin in the global square-corner reset) */
.more-spin { display: inline-block; width: 11px; height: 11px; margin-right: 6px;
             vertical-align: -1px; border-radius: 50%;
             border: 1.5px solid var(--border); border-top-color: var(--brand);
             animation: fb-rot .7s linear infinite; }
</style>
