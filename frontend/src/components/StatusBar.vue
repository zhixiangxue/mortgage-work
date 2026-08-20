<script setup>
import { computed } from "vue";
import { store, syncNow, modelLabel, openIndexing } from "../store.js";

/* Organizer label — only visible when running or recently done */
function organizerLabel() {
  const o = store.organizer;
  if (!o.running && !o.done) return null;
  if (o.running) return `ORGANIZER · sorting ${o.done}/${o.total} files…`;
  if (o.done) return `ORGANIZER · done — ${o.total} files`;
  return null;
}

/* Clerk label — only visible when actually processing (skip scanning so the
   bar stays quiet during the settle window and only pulses when work starts). */
function clerkLabel() {
  const c = store.clerk;
  if (c.state === "idle" || c.state === "scanning") return null;
  const client = c.client ? ` · ${c.client}` : "";
  if (c.state === "processing") return `CLERK${client} · ${c.phase || "working"}…`;
  if (c.state === "done") return `CLERK${client} · up to date`;
  if (c.state === "error") return `CLERK${client} · failed`;
  return null;
}

/* Knowledge chip — always present, three honest faces:
   working → PROCESSING n (amber pulse) · problems → n FAILED (red, calm)
   · quiet  → KNOWLEDGE · n (the library size, nothing more).
   Every number here is an INDEXING number, so the click lands on the
   Indexing Status tab; the data dashboard keeps its own activity-bar door. */
const knowledge = computed(() => {
  const k = store.knowledge;
  if (k.processing > 0)
    return { cls: "busy", label: `PROCESSING ${k.processing}` };
  if (k.failed > 0)
    return { cls: "failed", label: `${k.failed} FAILED` };
  return { cls: "ok", label: `KNOWLEDGE · ${k.total}` };
});
</script>

<template>
  <div id="statusbar">
    <span class="ctx">{{ store.sbCtx }}</span>
    <span class="warn">{{ store.sbWarn }}</span>
    <!-- Agent activity: organizer (green) and clerk (amber) share one slot -->
    <span v-if="organizerLabel()" class="agent-status organizer"
          :class="{ running: store.organizer.running }">{{ organizerLabel() }}</span>
    <span v-else-if="clerkLabel()" class="agent-status clerk"
          :class="{ running: store.clerk.state === 'scanning' || store.clerk.state === 'processing',
                    done: store.clerk.state === 'done',
                    err: store.clerk.state === 'error' }">{{ clerkLabel() }}</span>
    <span class="right">
      <!-- Two honest states, no ambiguity: demo book (browser dev) vs a
           workspace that failed to load. The error outlives the toast. -->
      <span v-if="store.demo" class="demo-flag"
            data-tip="Plain-browser dev mode — everything shown is demo data">◆ DEMO DATA</span>
      <span v-else-if="!store.repo && store.bootError" class="demo-flag"
            :data-tip="'Workspace load failed: ' + store.bootError"
        >◆ WORKSPACE OFFLINE · {{ store.bootError }}</span>
      <span>{{ store.sbRight }}</span>
      <span id="sb-sync" :class="store.sync.cls" @click="syncNow()"
            data-tip="Backed up automatically — click to sync now">{{ store.sync.label }}</span>
      <!-- Knowledge Base chip: the numbers are indexing numbers, so the
           click lands on the Indexing Status tab. Working pulses, problems
           show a count, and everything healthy is just a library size. -->
      <span id="sb-knowledge" :class="knowledge.cls" @click="openIndexing()"
            :data-tip="knowledge.cls === 'failed'
              ? 'Some documents need attention — click to open Indexing Status'
              : knowledge.cls === 'busy'
              ? 'Documents are being indexed — click to open Indexing Status'
              : 'The indexing pipeline — click to open Indexing Status'">
        <span class="kb-dot"></span>{{ knowledge.label }}
      </span>
      <!-- Nothing in settings.yaml means nothing to talk to — say so here too -->
      <span>{{ (modelLabel(store.currentModel) || "no model").toUpperCase() }}</span>
    </span>
  </div>
</template>

<style scoped>
#statusbar {
  height: 26px; background: var(--bg);
  border-top: 1px solid var(--border);
  display: flex; align-items: center;
  padding: 0 14px; gap: 18px;
  font: 500 10px var(--mono); letter-spacing: 1px; text-transform: uppercase;
  color: var(--text-3); flex-shrink: 0; user-select: none;
  /* One line, always — long contexts truncate, they never wrap the bar */
  white-space: nowrap; overflow: hidden;
}
/* Status text uses the softened --sb-* hues from global.css — full-strength
   brand/amber read as noise here; the tokens keep the hue, drop the shout.
   (color-mix() is off the table: WKWebView silently drops it.) */
#statusbar .ctx { color: var(--sb-brand); min-width: 0; overflow: hidden; text-overflow: ellipsis; }
/* Warnings give way first (shrink harder) — the client context is the anchor */
#statusbar .warn { color: var(--sb-amber); min-width: 0; overflow: hidden; text-overflow: ellipsis; flex-shrink: 4; }
#statusbar .right { margin-left: auto; display: flex; gap: 18px; flex-shrink: 0; }
/* Sync indicator — git under the hood, Dropbox language on the surface */
#sb-sync { cursor: pointer; }
#sb-sync.ok { color: var(--sb-brand); }
#sb-sync.busy { color: var(--sb-amber); animation: pulse 1.1s infinite; }
/* Offline: commits are safe locally, push owed — amber but calm (no pulse) */
#sb-sync.off { color: var(--sb-amber); }
/* Knowledge Base door — quiet green when healthy, amber pulse while work
   is in flight, solid red when something needs attention */
#sb-knowledge { cursor: pointer; display: inline-flex; align-items: center; gap: 5px; }
/* A real circle, not the "●" glyph — the glyph renders heavy and uneven in
   the mono face. (Whitelisted in global.css's square-corner reset.) */
.kb-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; flex: none; }
#sb-knowledge.ok { color: var(--sb-brand); }
#sb-knowledge.busy { color: var(--sb-amber); animation: pulse 1.1s infinite; }
#sb-knowledge.failed { color: var(--red); }
.demo-flag {
  color: var(--sb-amber);
  /* Boot errors can be long — keep the bar intact */
  max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* ── Agent status (organizer / clerk) ── */
.agent-status {
  display: inline-flex; align-items: center; gap: 5px;
  min-width: 0; overflow: hidden; text-overflow: ellipsis;
}
.agent-status.organizer { color: var(--sb-brand); }
.agent-status.clerk { color: var(--sb-amber); }
.agent-status.running { animation: pulse 1.1s infinite; }
.agent-status.done { color: var(--sb-brand); }
.agent-status.err { color: var(--red); }
</style>
