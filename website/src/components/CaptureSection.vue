<template>
  <section id="capture" class="capture">
    <div class="shell">
      <div class="section-head">
        <p class="section-eyebrow"><span class="dot"></span> Every call becomes context</p>
        <h2>The AI hears what you hear.</h2>
        <p>
          A coin-sized recorder you carry everywhere — desk calls, client
          meetings, coffee with a referral partner. It transcribes in real time
          and drops the notes straight into the client's folder — so the agent
          always knows the latest, even the stuff clients say but never write down.
        </p>
      </div>

      <div class="capture-demo">
        <!-- Left: phone icon with ripple -->
        <div class="cap-source">
          <div class="ripple-ring" :class="{ live: recording }"></div>
          <div class="ripple-ring delay" :class="{ live: recording }"></div>
          <div class="cap-circle">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/>
            </svg>
          </div>
          <span class="cap-source-label">Call · Sarah Mitchell</span>
        </div>

        <!-- Arrow -->
        <div class="cap-arrow">
          <svg viewBox="0 0 80 24" width="80" height="24" fill="none" stroke="currentColor" stroke-width="1" stroke-dasharray="4 4" stroke-linecap="round">
            <line x1="2" y1="12" x2="70" y2="12" class="dash-flow"/>
            <path d="m68 8 6 4-6 4"/>
          </svg>
        </div>

        <!-- Right: transcript as chat bubbles -->
        <div class="transcript-card">
          <div class="transcript-head">
            <span class="th-path">sarah-mitchell / notes / call-07-28.md</span>
            <span class="th-status" :class="{ saved: transcriptSaved }">
              {{ transcriptSaved ? '✓ saved' : 'transcribing…' }}
            </span>
          </div>
          <div class="transcript-body">
            <TransitionGroup name="bubble">
              <div v-for="(line, i) in visibleTranscript" :key="i" class="bubble-row" :class="line.role">
                <span class="bubble">{{ line.text }}</span>
              </div>
            </TransitionGroup>
            <div v-if="!transcriptSaved" class="bubble-row" :class="typingSide">
              <span class="bubble typing-dots"><span></span><span></span><span></span></span>
            </div>
          </div>
        </div>

        <!-- Arrow → agent -->
        <div class="cap-arrow" :class="{ active: transcriptSaved }">
          <svg viewBox="0 0 80 24" width="80" height="24" fill="none" stroke="currentColor" stroke-width="1" stroke-dasharray="4 4" stroke-linecap="round">
            <line x1="2" y1="12" x2="70" y2="12" class="dash-flow"/>
            <path d="m68 8 6 4-6 4"/>
          </svg>
        </div>

        <!-- Agent icon -->
        <div class="cap-dest" :class="{ active: transcriptSaved }">
          <div class="cap-circle">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 8V4H8"/>
              <rect x="4" y="8" width="16" height="12" rx="0"/>
              <path d="M2 14h2M20 14h2M12 8v4M9 14h.01M15 14h.01"/>
            </svg>
          </div>
          <span class="cap-source-label">Agent processing</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const recording = ref(true)
const transcriptSaved = ref(false)
const visibleTranscript = ref([])

// Next typing indicator aligns to whichever side speaks next
const typingSide = computed(() =>
  visibleTranscript.value.length < transcript.length
    ? transcript[visibleTranscript.value.length].role
    : 'lo'
)

const transcript = [
  { role: 'client', text: 'I just got a raise — base went up to $140K starting next month.' },
  { role: 'lo', text: 'Great, do you have the offer letter? That could change your DTI.' },
  { role: 'client', text: 'Yeah, I\'ll email it over. Also my employer matches my 401k — does that count?' },
]

let timer = null

onMounted(() => {
  let idx = 0
  const typeLine = () => {
    if (idx < transcript.length) {
      visibleTranscript.value.push(transcript[idx])
      idx++
      timer = setTimeout(typeLine, 1600)
    } else {
      timer = setTimeout(() => {
        transcriptSaved.value = true
        timer = setTimeout(() => {
          visibleTranscript.value = []
          transcriptSaved.value = false
          idx = 0
          timer = setTimeout(typeLine, 800)
        }, 5000)
      }, 1000)
    }
  }
  timer = setTimeout(typeLine, 800)
})

onUnmounted(() => clearTimeout(timer))
</script>
