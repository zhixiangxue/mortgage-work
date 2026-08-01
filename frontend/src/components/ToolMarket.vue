<script setup>
/* Tool Market — the browse-and-install surface (VS Code extensions model,
   in LO language). Opens as a tab in the editor area from the Tools panel's
   EXPLORE card. Installed tools show a check and can only be removed from
   the sidebar panel — one place to manage what's active. */
import { store, installTool } from "../store.js";
</script>

<template>
  <div id="doc-area" class="tm-wrap">
    <div class="tm-head">
      <div class="tm-title">TOOL MARKET</div>
      <div class="tm-sub">New skills for your assistant — one click away.</div>
    </div>
    <div class="tm-grid">
      <div v-for="s in store.skills" :key="s.id" class="tm-card" :class="{ have: s.installed }">
        <div class="tm-row1">
          <span class="tm-name">{{ s.name }}</span>
          <span v-if="s.version" class="tm-tag">{{ s.version }}</span>
        </div>
        <div class="tm-desc">{{ s.description }}</div>
        <div class="tm-foot">
          <span v-if="s.installed" class="tm-installed">✓ INSTALLED</span>
          <!-- Install = uv sync inside the skill directory (real bridge call).
               The button just shows a busy state while it runs. -->
          <button v-else class="btn-sm primary tm-btn" :class="{ busy: s.busy }"
                  @click="installTool(s)">
            <span class="tm-lbl">{{ s.busy ? "INSTALLING…" : "INSTALL" }}</span>
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
/* Install button: fixed width so INSTALL → INSTALLING… doesn't wobble */
.tm-btn { position: relative; overflow: hidden; min-width: 96px; }
.tm-lbl { position: relative; }
/* Busy: hollow shell, dimmed — the real work is a single bridge call */
.tm-btn.busy { background: var(--bg-raise); border-color: var(--border-soft); color: var(--text-2); cursor: default; }
</style>
