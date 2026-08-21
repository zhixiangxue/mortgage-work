<script setup>
/* Free-plan upgrade board — shown by every knowledge-base pane (units,
   graph) when the session has no KB plan. Guidance only: the Plan tab
   owns every redemption/billing control, so this card never duplicates
   that UI, it just opens it. */
import { openPlan } from "../store.js";
</script>

<template>
  <div class="upgrade">
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
</template>

<style scoped>
/* The whole pane is one quiet card, vertically centred so nothing
   competes with it */
.upgrade { flex: 1; min-height: 0; overflow-y: auto; display: flex;
           align-items: center; justify-content: center; padding: 24px 20px; }
.up-card { width: 100%; max-width: 520px; background: var(--bg-panel);
           border: 1px solid var(--border); padding: 26px 30px; }
.up-t { font-size: 14.5px; font-weight: 600; margin-bottom: 10px; }
.up-m { color: var(--text-4); font-size: 12px; line-height: 1.65; }
.up-perks { margin: 16px 0 20px; display: flex; flex-direction: column; gap: 6px;
            color: var(--text-2); font-size: 12px; }
.up-btn { align-self: flex-start; }
</style>
