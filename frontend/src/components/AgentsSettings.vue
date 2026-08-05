<script setup>
/* Settings — AGENTS.md. The LO's personal workspace instructions: preferences,
   rules, and context that get injected into the chat agent's system prompt on
   every new conversation. Stored at the repo root so it syncs across machines.

   Same shape as ModelSettings: a component-backed pane that reads/writes through
   the bridge. Auto-saves with a debounce; the status line shows saved/saving. */
import { ref, computed, onMounted, onUnmounted } from "vue";
import { loadAgentsMd, saveAgentsMd } from "../store.js";

const BOOTSTRAP = `# My Workspace Instructions

<!-- This file personalizes your AI assistant across every chat. -->
<!-- Edit freely — it syncs with your repo and follows you across machines. -->

## Focus
<!-- What loan types or borrower segments do you specialize in? -->
<!-- e.g. DSCR investment loans in Southern California, non-QM first. -->

## Communication Style
<!-- How should the assistant talk to you and your clients? -->
<!-- e.g. Formal tone with clients. Always flag missing docs before pre-approval. -->

## Rules
<!-- Hard rules the assistant must always follow. -->
<!-- e.g. Never quote income figures without verifying against source documents. -->
<!-- e.g. Use Pacific Time for all dates. -->

## Lender Preferences
<!-- Which lenders do you reach for first, and in what order? -->
<!-- e.g. itrust for non-QM, JMAC for FHA, NewWave for bank statement programs. -->
`;

const text = ref("");
const status = ref("idle");     // idle | loading | saving | saved | dirty
let saveTimer = null;

const statusLabel = computed(() => {
  switch (status.value) {
    case "loading": return "Loading…";
    case "saving": return "Saving…";
    case "saved": return "Saved";
    case "dirty": return "Editing…";
    default: return "";
  }
});

onMounted(() => {
  status.value = "loading";
  loadAgentsMd().then(res => {
    if (res && res.error) {
      status.value = "idle";
      return;
    }
    // First time: prefill the bootstrap template so the LO knows what to write.
    text.value = res.exists && res.content ? res.content : BOOTSTRAP;
    status.value = "idle";
  });
});

onUnmounted(() => {
  clearTimeout(saveTimer);
});

function onInput() {
  status.value = "dirty";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(doSave, 2000);
}

function doSave() {
  status.value = "saving";
  saveAgentsMd(text.value).then(res => {
    if (res && res.ok) {
      status.value = "saved";
      // Fade back to idle so "saved" doesn't linger forever
      setTimeout(() => {
        if (status.value === "saved") status.value = "idle";
      }, 3000);
    } else {
      status.value = "dirty";
    }
  });
}
</script>

<template>
  <div id="doc-area">
    <div class="md-doc">
      <h1>
        Workspace Instructions
        <span class="status-tag" :class="status" v-if="statusLabel">{{ statusLabel }}</span>
      </h1>
      <p class="path-line">
        What you write here shapes every chat — the content of <code>AGENTS.md</code>
        is injected into the assistant's context at the start of each new conversation.
        It lives at the repo root and syncs across your machines.
      </p>

      <textarea
        class="agents-editor"
        v-model="text"
        @input="onInput"
        spellcheck="false"
        placeholder="Write your preferences, rules, and context here…"
      ></textarea>
    </div>
  </div>
</template>

<style scoped>
.path-line { margin: 14px 0 4px; font: 400 11px var(--mono); color: var(--text-4); }
.path-line code { font-family: var(--mono); color: var(--text-2); }

.status-tag {
  margin-left: auto;
  font: 400 9px/1 var(--mono); letter-spacing: 1px; text-transform: uppercase;
  padding: 4px 8px; border: 1px solid var(--border-soft);
  color: var(--text-4); white-space: nowrap;
}
.status-tag.dirty { color: var(--text-3); border-color: var(--border); }
.status-tag.saving { color: var(--text-2); border-color: var(--brand); }
.status-tag.saved { color: var(--brand); border-color: var(--brand); }
.status-tag.loading { color: var(--text-4); }

/* Auto-saving markdown editor — monospace, generous height, IDE-like */
.agents-editor {
  width: 100%;
  min-height: 520px;
  margin-top: 16px;
  padding: 16px;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  font: 400 12.5px/1.7 var(--mono);
  resize: vertical;
  outline: none;
  tab-size: 2;
}
.agents-editor:focus { border-color: var(--brand); }
</style>
