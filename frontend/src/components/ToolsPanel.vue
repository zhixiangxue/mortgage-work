<script setup>
/* LO-facing tool panel: each card is one INSTALLED skill from the market
   repo with a health dot, a permission toggle ("can the agent use this") and
   a remove affordance. New skills come from the Tool Market — the ⌕ header
   action — ChatGPT-connectors style, not IDE JSON config. */
import { computed } from "vue";
import { store, showToast, setToolsStatus, openToolMarket, removeTool, toggleSkill } from "../store.js";

const installed = computed(() => store.skills.filter(s => s.installed));
</script>

<template>
  <div class="wrap">
    <div class="panel-header">Tools
      <!-- Same header-action idiom as the client list's ＋ / ⟳; blocks-with-one-
           incoming is the extensions-market glyph — "add pieces to your kit" -->
      <span class="icons">
        <span class="mkt" data-tip="Explore the tool market" @click="openToolMarket()">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round">
            <rect x="3" y="3" width="8" height="8"/>
            <rect x="3" y="13" width="8" height="8"/>
            <rect x="13" y="13" width="8" height="8"/>
            <path d="M17 2v7M13.5 5.5h7"/>
          </svg>
        </span>
      </span>
    </div>

    <div class="cards">
      <div v-for="s in installed" :key="s.id" class="card" :class="{ off: !s.enabled }">
        <div class="row1">
          <span class="dot" :class="{ up: s.enabled }"></span>
          <span class="tname">{{ s.name }}</span>
          <!-- Uninstall lives here, next to the switch — the market only installs.
               Same trash shape as chat's delete; no inner lines, stays crisp small -->
          <span class="rm" data-tip="Remove this tool" @click="removeTool(s)">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
            </svg>
          </span>
          <!-- Permission switch: LO decides what the agent may touch -->
          <span class="switch" :class="{ on: s.enabled }"
                :data-tip="s.enabled ? 'Agent may use this skill — click to disable' : 'Disabled — click to allow'"
                @click="toggleSkill(s)"><span class="knob"></span></span>
        </div>
        <div class="desc">{{ s.description }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow-y: auto; }
/* SVG header action: kill the inline-baseline gap the text glyphs don't have */
.icons .mkt { display: flex; align-items: center; }
.cards { display: flex; flex-direction: column; gap: 8px; padding: 4px 14px 14px; }
.card { padding: 10px 12px; background: var(--bg-panel); border: 1px solid var(--border); }
.card.off .tname, .card.off .desc { color: var(--text-4); }
.row1 { display: flex; align-items: center; gap: 8px; }
.tname { font: 600 12px var(--mono); color: var(--text-2); }
.desc { margin-top: 6px; padding-left: 14px; font: 400 10px var(--mono); color: var(--text-4); }
/* Health dot — same vocabulary as the runtime panel; grey when switched off */
.dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; background: var(--text-4); }
.dot.up { background: var(--brand); }
/* Remove: quiet until hovered, red on intent — the IDE close-button idiom */
.rm {
  margin-left: auto; flex-shrink: 0; cursor: pointer;
  display: flex; align-items: center; padding: 0 2px;
  color: transparent;
}
.card:hover .rm { color: var(--text-4); }
.rm:hover { color: var(--red); }
/* Permission toggle — small IDE-style switch, brand green when on */
.switch {
  flex-shrink: 0; cursor: pointer;
  width: 26px; height: 14px; padding: 2px;
  background: var(--bg-raise); border: 1px solid var(--border-soft);
  display: flex; align-items: center; transition: background .15s;
}
.switch .knob {
  width: 10px; height: 10px; background: var(--text-4);
  transition: transform .15s, background .15s;
}
.switch.on { background: var(--brand); border-color: var(--brand); }
.switch.on .knob { transform: translateX(12px); background: var(--on-brand); }
</style>
