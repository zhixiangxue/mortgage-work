<script setup>
import { computed, onBeforeUnmount, onMounted, ref, nextTick, watch } from "vue";

// ── Log format: "HH:MM:SS LEVEL [module] message" ──
// LEVEL is padded to 5 chars (e.g. "INFO ", "WARN ", "ERROR", "DEBUG")
const LOG_RE = /^(\d{2}:\d{2}:\d{2})\s+(DEBUG|INFO\s|WARN\s|ERROR)\s+\[([^\]]+)\]\s+(.*)$/;

const rawLines = ref([]);
const logEl = ref(null);
const autoScroll = ref(true);
const filter = ref("ALL");  // ALL | ERROR | WARN | INFO | DEBUG
const search = ref("");
let timer = null;

// ── Parse & filter ──
const entries = computed(() => {
  let list = [];
  for (const line of rawLines.value) {
    const m = line.match(LOG_RE);
    if (m) {
      list.push({
        raw: line,
        level: m[2].trim(),
        ts: m[1],
        module: m[3],
        msg: m[4],
      });
    } else {
      // Unparseable line (startup banner, stack trace, etc.)
      list.push({ raw: line, level: "", ts: "", module: "", msg: line });
    }
  }
  // Filter by level
  if (filter.value !== "ALL") {
    list = list.filter(e => e.level === filter.value);
  }
  // Search
  if (search.value) {
    const q = search.value.toLowerCase();
    list = list.filter(e => e.raw.toLowerCase().includes(q));
  }
  return list;
});

const filterCounts = computed(() => {
  const counts = { ALL: rawLines.value.length, ERROR: 0, WARN: 0, INFO: 0, DEBUG: 0 };
  for (const line of rawLines.value) {
    const m = line.match(LOG_RE);
    if (m) {
      const lv = m[2].trim();
      if (counts[lv] !== undefined) counts[lv]++;
    }
  }
  return counts;
});

// ── Fetch ──
async function fetchLog() {
  if (!window.pywebview) return;
  try {
    const res = await window.pywebview.api.tail_runtime_log(500);
    if (res && res.lines) {
      rawLines.value = res.lines;
      if (autoScroll.value) {
        await nextTick();
        if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight;
      }
    }
  } catch { /* not connected */ }
}

function onLogScroll() {
  if (!logEl.value) return;
  const el = logEl.value;
  autoScroll.value = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
}

function clearLog() {
  rawLines.value = [];
}

function setFilter(lv) { filter.value = lv; }

// ── Level class ──
function lvClass(lv) {
  switch (lv) {
    case "ERROR": return "lv-err";
    case "WARN":  return "lv-warn";
    case "DEBUG": return "lv-dbg";
    default:      return "";
  }
}

// Re-scroll when filter/search changes (only if autoScroll is on)
watch([filter, search], async () => {
  if (autoScroll.value) {
    await nextTick();
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight;
  }
});

onMounted(() => {
  fetchLog();
  timer = setInterval(fetchLog, 1000);
});

onBeforeUnmount(() => {
  clearInterval(timer);
});
</script>

<template>
  <div class="lv-root">
    <!-- Toolbar -->
    <div class="lv-toolbar">
      <span class="lv-title">Console</span>

      <!-- Level filter chips -->
      <span class="lv-filters">
        <button v-for="lv in ['ALL','ERROR','WARN','INFO','DEBUG']" :key="lv"
                :class="['lv-chip', { on: filter === lv }]"
                @click="setFilter(lv)">
          {{ lv }}<span v-if="filterCounts[lv]" class="lv-chip-n">{{ filterCounts[lv] }}</span>
        </button>
      </span>

      <!-- Search -->
      <input class="lv-search" v-model="search" placeholder="Search…" spellcheck="false" />

      <span class="lv-actions">
        <span class="lv-meta">{{ entries.length }}/{{ rawLines.length }} lines</span>
        <button class="lv-clear" @click="clearLog">Clear</button>
      </span>
    </div>

    <!-- Log body -->
    <div class="lv-body" ref="logEl" @scroll="onLogScroll">
      <div v-if="entries.length === 0" class="lv-empty">
        {{ rawLines.length === 0 ? 'Waiting for output…' : 'No matching lines.' }}
      </div>
      <div v-for="(e, i) in entries" :key="i" :class="['lv-line', lvClass(e.level)]">
        <span v-if="e.ts" class="lv-ts">{{ e.ts }}</span>
        <span v-if="e.level" :class="['lv-tag', lvClass(e.level)]">{{ e.level }}</span>
        <span v-if="e.module" class="lv-mod">[{{ e.module }}]</span>
        <span class="lv-msg">{{ e.msg }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lv-root {
  display: flex; flex-direction: column;
  flex: 1; min-height: 0; background: var(--bg);
}

/* ── Toolbar ── */
.lv-toolbar {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 16px; background: var(--bg-hover);
  border-bottom: 1px solid var(--border); user-select: none; flex-shrink: 0;
}
.lv-title {
  font: 500 12px var(--mono); color: var(--text-3);
  flex-shrink: 0;
}

/* Level filter chips */
.lv-filters { display: flex; gap: 4px; }
.lv-chip {
  padding: 2px 8px; border-radius: 3px; cursor: pointer;
  font: 500 9.5px var(--mono); color: var(--text-4);
  background: none; border: 1px solid var(--border-soft);
  transition: .12s; display: inline-flex; align-items: center; gap: 4px;
}
.lv-chip:hover { border-color: var(--text-4); color: var(--text-3); }
.lv-chip.on { border-color: var(--brand); color: var(--brand); background: color-mix(in srgb, var(--brand) 12%, transparent); }
.lv-chip-n { font-size: 8.5px; opacity: .6; }

/* Search */
.lv-search {
  flex: 1; min-width: 0; max-width: 220px;
  padding: 3px 8px; border-radius: 3px;
  font: 400 10.5px var(--mono); color: var(--text-2);
  background: var(--bg); border: 1px solid var(--border);
  outline: none;
}
.lv-search:focus { border-color: var(--brand); }
.lv-search::placeholder { color: var(--text-4); }

.lv-actions { margin-left: auto; display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.lv-meta {
  font: 400 10px var(--mono); color: var(--text-4);
}
.lv-clear {
  padding: 3px 12px; border-radius: 4px; cursor: pointer;
  font: 500 10.5px var(--sans); color: var(--text-3);
  background: var(--bg); border: 1px solid var(--border);
}
.lv-clear:hover { border-color: var(--brand); color: var(--brand); }

/* ── Body ── */
.lv-body {
  flex: 1; min-height: 0; overflow-y: auto;
  background: color-mix(in srgb, var(--bg-editor) 85%, #000);
  font: 400 12px / 1.5 var(--mono);
  padding: 6px 0;
  user-select: text;
}
.lv-line {
  display: flex; align-items: baseline; gap: 6px;
  padding: 1px 16px;
  white-space: nowrap;
  min-height: 20px;
}
.lv-line:hover { background: var(--bg-hover); }

/* Parts */
.lv-ts   { flex-shrink: 0; width: 68px; font-size: .85em; opacity: .45; }
.lv-tag  { flex-shrink: 0; width: 42px; font-size: .82em; font-weight: 600; text-align: center; }
.lv-mod  { flex-shrink: 0; font-size: .85em; opacity: .55; max-width: 180px; overflow: hidden; text-overflow: ellipsis; }
.lv-msg  { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }

/* Level colours */
.lv-err  { color: #f85149; }
.lv-warn { color: #d29922; }
.lv-dbg  { color: var(--text-4); opacity: .7; }
.lv-line.lv-err  { background: rgba(248,81,73,.06); }
.lv-line.lv-warn { background: rgba(210,153,34,.05); }
.lv-line.lv-err:hover  { background: rgba(248,81,73,.14); }
.lv-line.lv-warn:hover { background: rgba(210,153,34,.12); }

.lv-empty {
  padding: 40px 20px;
  font: 400 12px var(--sans); color: var(--text-4);
  text-align: center;
}
</style>
