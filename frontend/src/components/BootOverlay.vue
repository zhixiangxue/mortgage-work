<script setup>
import { ref, onMounted } from "vue";

// Terminal-style startup, not a spinner — timings match the old inline boot
const LINES = [
  ["models.yaml", "3 providers"],
  ["clients/", "12 folders"],
  ["index · vector + graph", "warm"],
  ["cloud backup", "up to date"],
];

const onCount = ref(0);
const readyOn = ref(false);
const out = ref(false);
const gone = ref(false);

onMounted(() => {
  LINES.forEach((_, i) => setTimeout(() => { onCount.value = i + 1; }, 160 + i * 150));
  const done = 160 + LINES.length * 150;
  setTimeout(() => { readyOn.value = true; }, done + 100);
  setTimeout(() => {
    out.value = true;
    // Drop the overlay from the DOM once the fade finishes
    setTimeout(() => { gone.value = true; }, 600);
  }, done + 520);
});
</script>

<template>
  <div id="boot" v-if="!gone" :class="{ out }">
    <div id="boot-box">
      <div id="boot-logo"><span class="mark">M</span><span class="word">MORTGAGE <b>WORK</b></span></div>
      <div class="bl" v-for="(l, i) in LINES" :key="i" :class="{ on: i < onCount }">
        <span>{{ l[0] }}</span><span class="dots"></span><span class="ok">{{ l[1] }}</span>
      </div>
      <div id="boot-ready" :class="{ on: readyOn }">ready. <span class="cur"></span></div>
    </div>
  </div>
</template>

<style scoped>
#boot {
  position: fixed; inset: 0; z-index: 999; background: #000;
  display: flex; align-items: center; justify-content: center;
  transition: opacity .5s ease;
}
#boot.out { opacity: 0; pointer-events: none; }
#boot-box { width: 340px; font: 400 11.5px var(--mono); }
#boot-logo { display: flex; align-items: center; gap: 9px; margin-bottom: 22px; }
#boot-logo .mark {
  width: 22px; height: 22px; background: var(--brand); color: #000;
  font: 700 13px var(--mono); display: flex; align-items: center; justify-content: center;
}
#boot-logo .word { font: 700 12px var(--mono); letter-spacing: 2px; color: var(--text); }
#boot-logo .word b { color: var(--brand); }
.bl {
  display: flex; align-items: baseline; gap: 10px; margin: 8px 0; color: var(--text-3);
  opacity: 0; transform: translateY(4px); transition: opacity .28s, transform .28s;
}
.bl.on { opacity: 1; transform: none; }
.bl .dots { flex: 1; border-bottom: 1px dotted #2a2a2a; }
.bl .ok { color: var(--brand); }
#boot-ready { margin-top: 18px; color: var(--text); opacity: 0; transition: opacity .3s; }
#boot-ready.on { opacity: 1; }
#boot-ready .cur {
  display: inline-block; width: 7px; height: 13px; background: var(--brand);
  vertical-align: -2px; animation: bblink 1s steps(1) infinite;
}
@keyframes bblink { 50% { opacity: 0; } }
</style>
