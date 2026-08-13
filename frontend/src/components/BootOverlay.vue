<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { store, countFiles } from "../store.js";
import { retryBoot } from "../main.js";

/* Terminal-style startup, not a spinner — but the curtain is real now:
   lines cascade only after the workspace snapshot lands (bootDone), and the
   figures on them are whatever the scan actually found. While git clones or
   pulls, the overlay narrates the backend's own progress — Python pushes
   boot stages (cloning / pulling / restoring / scanning) through
   setBootState, so the user sees WHAT is happening, not a frozen screen.

   One exception: when the workspace FAILED to load (bootError, no repo), the
   overlay becomes a gate instead of a curtain. It stays up, says what went
   wrong in one sentence, and offers exactly one action — RETRY — so a demo
   machine with a flaky network still has a path in. The gate only shows when
   the snapshot already answered (bootDone); while the answer is in flight the
   curtain holds as usual. */

const onCount = ref(0);
const readyOn = ref(false);
const out = ref(false);
const gone = ref(false);

// The workspace couldn't load and there is nothing to fall back on. Only
// bridge-backed runs can retry — a plain browser has no backend to ask.
const gated = computed(() => store.bootDone && !!store.bootError && !store.repo);
const retryable = computed(() => gated.value && !!window.pywebview);

// The backend's first-run stages, in words a person reads as progress.
const STAGE_TEXT = {
  cloning: "downloading workspace…",
  pulling: "syncing workspace…",
  restoring: "repairing workspace…",
  scanning: "reading workspace…",
  retrying: "retrying…",
  waiting: "waiting for desktop backend…",
};
const stageText = computed(() => {
  const s = store.bootStage && store.bootStage.stage;
  return STAGE_TEXT[s] || "syncing…";
});

// Facts from the loaded workspace — real repo after hydration, mocks in
// plain-browser dev. Computed once at reveal time (lines() runs post-boot).
const lines = computed(() => {
  const repoLbl = store.bootError ? "unavailable · offline"
    : store.repo ? store.repo.path.split("/").pop() : "local mocks";
  const lenders = store.productTree.filter(n => n.type === "dir").length;
  return [
    ["work repo", repoLbl],
    ["clients/", `${store.clients.length} active · ${store.closed.length} closed`],
    ["products/", `${lenders} lenders · ${countFiles(store.productTree)} docs`],
  ];
});

function reveal() {
  lines.value.forEach((_, i) => setTimeout(() => { onCount.value = i + 1; }, 160 + i * 150));
  const done = 160 + lines.value.length * 150;
  setTimeout(() => { readyOn.value = true; }, done + 100);
  setTimeout(() => {
    out.value = true;
    // Drop the overlay from the DOM once the fade finishes
    setTimeout(() => { gone.value = true; }, 600);
  }, done + 520);
}

// Boot may already be done (fast pull / hot reload) or still syncing
onMounted(() => { if (store.bootDone && !gated.value) reveal(); });
watch(() => store.bootDone, done => { if (done && !gated.value) reveal(); });
// A successful gate retry clears bootError while bootDone is already true —
// the transition out of the gate is what releases the curtain.
watch(gated, g => { if (!g && store.bootDone) reveal(); });
</script>

<template>
  <div id="boot" v-if="!gone" :class="{ out }">
    <div id="boot-box">
      <div id="boot-logo"><span class="mark">M</span><span class="word">MORTGAGE <b>WORK</b></span></div>
      <div v-if="!store.bootDone" class="bl on hold">
        <span>work repo</span><span class="dots"></span><span class="wait">{{ stageText }}</span>
      </div>
      <template v-else-if="gated">
        <div class="gate-panel">
          <div class="gate-title">WORKSPACE NOT READY</div>
          <div class="gate-detail">{{ store.bootError }}</div>
          <div class="gate-hint">
            Mortgage Work downloads your workspace on first launch.
            Check the connection and try again.
          </div>
          <button v-if="retryable" class="gate-btn"
                  :disabled="store.bootRetrying" @click="retryBoot">
            {{ store.bootRetrying ? "DOWNLOADING…" : "TRY AGAIN" }}
          </button>
          <div v-else class="gate-hint">
            Restart the app to try again.
          </div>
        </div>
      </template>
      <template v-else>
        <div class="bl" v-for="(l, i) in lines" :key="i" :class="{ on: i < onCount }">
          <span>{{ l[0] }}</span><span class="dots"></span>
          <span :class="store.bootError && i === 0 ? 'err' : 'ok'">{{ l[1] }}</span>
        </div>
      </template>
      <div id="boot-ready" :class="{ on: readyOn }">ready. <span class="cur"></span></div>
    </div>
  </div>
</template>

<style scoped>
#boot {
  position: fixed; inset: 0; z-index: 999; background: var(--bg);
  display: flex; align-items: center; justify-content: center;
  transition: opacity .5s ease;
}
#boot.out { opacity: 0; pointer-events: none; }
#boot-box { width: 340px; font: 400 11.5px var(--mono); }
#boot-logo { display: flex; align-items: center; gap: 9px; margin-bottom: 22px; }
#boot-logo .mark {
  width: 22px; height: 22px; background: var(--brand); color: var(--on-brand);
  font: 700 13px var(--mono); display: flex; align-items: center; justify-content: center;
}
#boot-logo .word { font: 700 12px var(--mono); letter-spacing: 2px; color: var(--text); }
#boot-logo .word b { color: var(--brand); }
.bl {
  display: flex; align-items: baseline; gap: 10px; margin: 8px 0; color: var(--text-3);
  opacity: 0; transform: translateY(4px); transition: opacity .28s, transform .28s;
}
.bl.on { opacity: 1; transform: none; }
.bl .dots { flex: 1; border-bottom: 1px dotted var(--border-soft); }
.bl .ok { color: var(--brand); }
.bl .err { color: var(--red); }
/* Waiting on git — gentle pulse instead of fake progress */
.bl.hold .wait { color: var(--text-3); animation: bpulse 1.2s ease-in-out infinite; }
@keyframes bpulse { 50% { opacity: .35; } }
#boot-ready { margin-top: 18px; color: var(--text); opacity: 0; transition: opacity .3s; }
#boot-ready.on { opacity: 1; }
#boot-ready .cur {
  display: inline-block; width: 7px; height: 13px; background: var(--brand);
  vertical-align: -2px; animation: bblink 1s steps(1) infinite;
}
@keyframes bblink { 50% { opacity: 0; } }
/* ── Boot gate: the one-button recovery panel ── */
.gate-panel {
  margin-top: 4px; padding: 18px 16px 16px;
  border: 1px solid var(--red); border-radius: 4px;
  display: flex; flex-direction: column; gap: 10px; align-items: flex-start;
}
.gate-title {
  color: var(--red); font: 700 12px var(--mono); letter-spacing: 2px;
}
.gate-detail {
  color: var(--text-2); font: 400 11px/1.6 var(--mono);
  word-break: break-word;
}
.gate-hint { color: var(--text-3); font: 400 10.5px/1.6 var(--mono); }
.gate-btn {
  margin-top: 4px; padding: 8px 22px; cursor: pointer;
  background: var(--brand); color: var(--on-brand);
  border: none; border-radius: 3px;
  font: 700 11px var(--mono); letter-spacing: 2px;
}
.gate-btn:disabled { opacity: .55; cursor: wait; }
.gate-btn:not(:disabled):hover { filter: brightness(1.15); }
</style>
