<script setup>
import { store, closeHist, restoreVersion } from "../store.js";
</script>

<template>
  <div id="hist-overlay" v-show="store.hist.open" @click.self="closeHist()">
    <div id="hist-box">
      <div class="h-head"><span>{{ store.hist.title }}</span><span class="x" @click="closeHist()">✕</span></div>
      <div>
        <div v-for="(r, i) in store.hist.rows" :key="i" class="h-row">
          <span class="t">{{ r[0] }}</span>
          <span class="who" :class="{ ai: r[1] === 'AI' }">{{ r[1] }}</span>
          <span class="act">{{ r[2] }}</span>
          <!-- No revision = a placeholder row (no history yet, or an error) -->
          <button v-if="r[3]" class="btn-sm" @click="restoreVersion(r)">Restore</button>
        </div>
      </div>
      <div class="h-note">Every change is versioned automatically — nothing is ever lost.</div>
    </div>
  </div>
</template>

<style scoped>
#hist-overlay {
  position: fixed; inset: 0; background: rgba(0, 0, 0, .65); z-index: 200;
  display: flex; align-items: center; justify-content: center;
}
#hist-box { width: 560px; background: var(--bg-panel); border: 1px solid var(--border-soft); }
.h-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 13px 16px; border-bottom: 1px solid var(--border);
  font: 700 11px var(--mono); letter-spacing: 1.5px; color: var(--text);
}
.h-head .x { cursor: pointer; color: var(--text-4); font-size: 12px; }
.h-head .x:hover { color: var(--red); }
.h-row {
  display: flex; align-items: center; gap: 14px; padding: 10px 16px;
  border-bottom: 1px solid var(--border); font: 400 11px var(--mono); color: var(--text-2);
}
.h-row:last-child { border-bottom: none; }
.h-row .t { color: var(--text-4); width: 138px; flex-shrink: 0; }
.h-row .who { width: 32px; flex-shrink: 0; color: var(--text-3); font-weight: 700; font-size: 9px; letter-spacing: 1px; }
.h-row .who.ai { color: var(--brand); }
.h-row .act { flex: 1; text-align: left; }
.h-row .btn-sm { opacity: 0; }
.h-row:hover .btn-sm { opacity: 1; }
.h-note { padding: 10px 16px; font: 400 10px var(--mono); color: var(--text-4); }
</style>
