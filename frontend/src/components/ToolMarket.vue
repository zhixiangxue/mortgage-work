<script setup>
/* Tool Market — the browse-and-install surface (VS Code extensions model,
   in LO language). Opens as a tab in the editor area from the Tools panel's
   EXPLORE card. Installed tools show a check and can only be removed from
   the sidebar panel — one place to manage what's active. */
import { TOOLS } from "../mocks/tools.js";
import { installTool } from "../store.js";
</script>

<template>
  <div id="doc-area" class="tm-wrap">
    <div class="tm-head">
      <div class="tm-title">TOOL MARKET</div>
      <div class="tm-sub">New skills for your assistant — one click away.</div>
    </div>
    <div class="tm-grid">
      <div v-for="t in TOOLS" :key="t.id" class="tm-card" :class="{ have: t.installed }">
        <div class="tm-row1">
          <span class="tm-name">{{ t.name }}</span>
          <span class="tm-tag">{{ t.tag }}</span>
        </div>
        <div class="tm-desc">{{ t.desc }}</div>
        <div class="tm-foot">
          <span v-if="t.installed" class="tm-installed">✓ INSTALLED</span>
          <!-- Install is a real pipeline (download zip → unpack to skills dir),
               so the button narrates it: progress fill, then unpack stripes -->
          <button v-else class="btn-sm primary tm-btn" :class="{ busy: t.busy, unpack: t.phase === 'unpack' }"
                  @click="installTool(t)">
            <span v-if="t.busy && t.phase === 'download'" class="tm-fill" :style="{ width: t.prog + '%' }"></span>
            <span class="tm-lbl">{{ !t.busy ? "INSTALL" : t.phase === "download" ? Math.round(t.prog) + "%" : "UNPACKING" }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tm-wrap { overflow-y: auto; }
.tm-head { padding: 34px 40px 10px; }
.tm-title { font: 700 15px var(--mono); letter-spacing: 2px; color: var(--text); }
.tm-sub { margin-top: 8px; font: 400 11.5px var(--mono); color: var(--text-3); }
.tm-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px; padding: 18px 40px 60px;
}
.tm-card {
  display: flex; flex-direction: column; gap: 8px;
  padding: 14px 16px; background: var(--bg-panel); border: 1px solid var(--border);
}
.tm-card:hover { border-color: var(--border-soft); }
/* Installed cards recede — they're done; attention belongs to the shelf */
.tm-card.have { opacity: .45; }
.tm-card.have:hover { border-color: var(--border); }
.tm-row1 { display: flex; align-items: baseline; gap: 8px; }
.tm-name { font: 600 12.5px var(--mono); color: var(--text); }
.tm-tag {
  margin-left: auto; flex-shrink: 0;
  font: 700 8px var(--mono); letter-spacing: 1px; padding: 1.5px 5px;
  background: var(--bg-raise); color: var(--text-4); border: 1px solid var(--border);
}
.tm-desc { font: 400 10.5px var(--mono); color: var(--text-3); line-height: 1.5; flex: 1; }
.tm-foot { display: flex; align-items: center; }
.tm-installed { font: 400 9.5px var(--mono); letter-spacing: 1px; color: var(--text-4); }
/* Install button: fixed width so INSTALL → 47% → UNPACKING doesn't wobble */
.tm-btn { position: relative; overflow: hidden; min-width: 96px; }
.tm-lbl { position: relative; }
/* Download: hollow shell, brand fill grows left→right with the progress */
.tm-btn.busy { background: var(--bg-raise); border-color: var(--border-soft); color: var(--text-2); cursor: default; }
.tm-fill { position: absolute; inset: 0 auto 0 0; background: var(--brand); opacity: .35; transition: width .12s linear; }
/* Unpack: marching stripes — work with no measurable progress */
.tm-btn.unpack {
  background: repeating-linear-gradient(-45deg,
    var(--bg-raise) 0 6px, color-mix(in srgb, var(--brand) 20%, var(--bg-raise)) 6px 12px);
  background-size: 200% 100%;
  animation: tm-march .5s linear infinite;
}
@keyframes tm-march { to { background-position: -17px 0; } }
</style>
