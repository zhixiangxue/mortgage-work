<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { store, countFiles } from "../store.js";

/* Terminal-style startup, not a spinner — but the curtain is real now:
   lines cascade only after the workspace snapshot lands (bootDone), and the
   figures on them are whatever the scan actually found. While git clones or
   pulls, the overlay sits in a "syncing" hold instead of lying. */

const onCount = ref(0);
const readyOn = ref(false);
const out = ref(false);
const gone = ref(false);

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
onMounted(() => { if (store.bootDone) reveal(); });
watch(() => store.bootDone, done => { if (done) reveal(); });
</script>

<template>
  <div id="boot" v-if="!gone" :class="{ out }">
    <div id="boot-box">
      <div id="boot-logo"><span class="mark">M</span><span class="word">MORTGAGE <b>WORK</b></span></div>
      <div v-if="!store.bootDone" class="bl on hold">
        <span>work repo</span><span class="dots"></span><span class="wait">syncing…</span>
      </div>
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
</style>
