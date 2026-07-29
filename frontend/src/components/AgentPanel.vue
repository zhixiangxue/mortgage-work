<script setup>
/* Developer-facing runtime panel. One agent row — subs are tools, you watch
   them in traces. Services restart as one unit: it's a single docker compose. */
import { store, openDoc, showToast } from "../store.js";
import { MAIN, SERVICES } from "../mocks/agent.js";

function restartAgent() {
  if (MAIN.status === "restart") return;
  MAIN.status = "restart";
  showToast("Restarting main agent… tools rebinding (demo)");
  setTimeout(() => {
    MAIN.status = "running";
    // The point of the architecture: worker jobs live in the queue, not in this process
    showToast("main agent up · tools rebound · worker jobs unaffected (demo)");
  }, 1400);
}

function restartAll() {
  const targets = SERVICES.filter(s => s.status !== "restart");
  if (!targets.length) return;
  showToast(`docker compose restart · ${targets.length} containers (demo)`);
  targets.forEach((s, i) => {
    const prev = s.status;
    s.status = "restart";
    // Staggered recovery, like real containers coming back one by one
    setTimeout(() => {
      s.status = prev;
      if (i === targets.length - 1) showToast("All services up (demo)");
    }, 900 + i * 400);
  });
}
</script>

<template>
  <div class="wrap">
    <div class="panel-header">Agent Runtime</div>

    <div class="sect">AGENT
      <span class="sbtn" data-tip="Restart main agent — sub-agents are tools, they reload with it"
            @click="restartAgent">⟳</span>
    </div>
    <div class="rrow" :class="{ selected: store.active === 'ag_main' }"
         @click="openDoc('ag_main', 'runtime/main')">
      <span class="dot" :class="MAIN.status"></span>
      <span class="rname main">main</span>
      <span class="rbtn" data-tip="Restart main agent" @click.stop="restartAgent">⟳</span>
      <span class="rmeta">{{ MAIN.status === 'restart' ? 'restarting…' : 'traces →' }}</span>
    </div>

    <div class="sect">SERVICES
      <span class="sbtn" data-tip="docker compose restart — all containers" @click="restartAll">⟳</span>
    </div>
    <div v-for="s in SERVICES" :key="s.doc" class="rrow" :class="{ selected: store.active === s.doc }"
         @click="openDoc(s.doc, 'runtime/' + s.name)">
      <span class="dot" :class="s.status"></span>
      <span class="rname">{{ s.name }}</span>
      <span class="rmeta">{{ s.status === 'restart' ? 'restarting…' : s.meta }}</span>
    </div>

    <div class="foot">infra: docker compose · see repo README</div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow-y: auto; }
.sect {
  padding: 14px 14px 6px; font: 500 9.5px var(--mono);
  letter-spacing: 1.5px; color: var(--text-4);
  display: flex; align-items: center; justify-content: space-between;
}
.sbtn { cursor: pointer; font-size: 12px; letter-spacing: 0; }
.sbtn:hover { color: var(--brand); }
.rrow {
  display: flex; align-items: center; gap: 8px;
  height: 26px; padding: 0 14px; cursor: pointer;
  font: 400 12px var(--mono); color: var(--text-2); white-space: nowrap;
}
.rrow:hover { background: var(--bg-hover); }
.rrow.selected { background: var(--bg-raise); color: var(--text); box-shadow: inset 2px 0 0 var(--brand); }
.rname.main { color: var(--text); font-weight: 600; }
.rmeta { margin-left: auto; font-size: 10px; color: var(--text-4); }
/* Per-row restart: hidden until hover, like every IDE gutter action */
.rbtn { display: none; font-size: 12px; color: var(--text-4); cursor: pointer; }
.rrow:hover .rbtn { display: inline; }
.rbtn:hover { color: var(--brand); }
/* Status dots: green = up, amber = working */
.dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; background: var(--text-4); }
.dot.running, .dot.up { background: var(--brand); }
.dot.busy { background: var(--amber); animation: pulse 1.2s infinite; }
.dot.restart { background: var(--amber); animation: pulse .45s infinite; }
@keyframes pulse { 50% { opacity: .35; } }
.foot {
  margin-top: auto; padding: 10px 14px;
  font: 400 9.5px var(--mono); letter-spacing: .5px; color: var(--text-4);
  border-top: 1px solid var(--border);
}
</style>
