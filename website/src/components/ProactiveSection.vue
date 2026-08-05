<template>
  <section id="proactive" class="proactive">
    <div class="shell">
      <div class="section-head">
        <p class="section-eyebrow"><span class="dot"></span> Before you ask, it's already done</p>
        <h2>The agent works ahead, not on command.</h2>
        <p>
          It watches your pipeline, notices what's missing, and does the work
          before you even ask — so you can focus on your clients, not the
          busywork.
        </p>
      </div>

      <div class="console-demo">
        <div class="console-header">
          <span class="console-dots">
            <span class="dot-r"></span><span class="dot-y"></span><span class="dot-g"></span>
          </span>
          <span class="console-title">agent · clerk</span>
          <span class="console-time">{{ clockTime }}</span>
        </div>
        <div class="console-body">
          <div
            v-for="(line, i) in visibleLines"
            :key="i"
            class="console-line"
            :class="line.type"
          >
            <span class="cl-time">{{ line.t }}</span>
            <span v-if="line.type === 'cmd'" class="cl-prompt">$</span>
            <span class="cl-text" v-html="line.text"></span>
          </div>
          <div v-if="showCursor" class="console-line cmd">
            <span class="cl-time">{{ lastTime }}</span>
            <span class="cl-prompt">$</span>
            <span class="cl-cursor"></span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const clockTime = ref('')
const showCursor = ref(true)
const visibleLines = ref([])
const lastTime = ref('')

const fullLines = [
  { t: '08:12', type: 'sys', text: 'clerk started · watching 4 active clients' },
  { t: '08:12', type: 'sys', text: 'new file detected: <b>sarah-mitchell/income/paystub-jul.pdf</b>' },
  { t: '08:12', type: 'agent', text: 'reading paystub · extracting YTD, base, OT' },
  { t: '08:13', type: 'agent', text: 'cross-checking against <b>bank-stmt-jul.pdf</b> deposit on 06/30' },
  { t: '08:13', type: 'agent', text: 'DTI recalculated → <b>30.9%</b> (was 34.1%)' },
  { t: '08:13', type: 'agent', text: 'conventional 80% LTV now qualifies' },
  { t: '08:13', type: 'done', text: 'Sarah Mitchell — income analysis complete · saved to <b>ai/profile.ai</b>' },
]

let timer = null

const updateClock = () => {
  const d = new Date()
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  clockTime.value = `${h}:${m}`
}

onMounted(() => {
  updateClock()

  // Type out console lines one by one
  let idx = 0
  const tick = () => {
    if (idx < fullLines.length) {
      visibleLines.value.push(fullLines[idx])
      lastTime.value = fullLines[idx].t
      idx++
      showCursor.value = idx < fullLines.length
      timer = setTimeout(tick, idx === fullLines.length - 1 ? 600 : 850)
    } else {
      // Restart cycle after a pause
      timer = setTimeout(() => {
        visibleLines.value = []
        idx = 0
        showCursor.value = true
        tick()
      }, 5000)
    }
  }
  // Small initial delay
  timer = setTimeout(tick, 400)
})

onUnmounted(() => clearTimeout(timer))
</script>
