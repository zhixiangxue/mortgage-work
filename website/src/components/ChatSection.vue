<template>
  <section id="chat" class="chat-sec">
    <div class="shell">
      <div class="section-head">
        <p class="section-eyebrow"><span class="dot"></span> Your team already has a chat app</p>
        <h2>Chat where you already are. The agent does the work.</h2>
        <p>
          Slack, Feishu, DingTalk, WeCom — your messages flow into Mortgage
          Work, where the agent opens the full client file, runs the numbers,
          and replies back in the same thread you started in.
        </p>
      </div>

      <div class="im-demo">
        <!-- Left: IM platforms. Messages flow in, agent replies flow back. -->
        <div class="im-spokes">
          <div
            v-for="(p, i) in platforms"
            :key="p.id"
            class="im-row"
            :class="{ active: activeIdx === i && stage >= 1 }"
          >
            <div class="im-main">
              <div class="im-head">
                <span class="im-ico" :class="{ replied: activeIdx === i && stage >= 2 }">
                  <svg v-if="activeIdx === i && stage >= 2" class="im-check" viewBox="0 0 10 10" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M1.5 5.5 4 8l4.5-6"/>
                  </svg>
                  <template v-else>{{ p.mono }}</template>
                </span>
                <span class="im-name">{{ p.name }}</span>
              </div>
              <div class="im-bubbles">
                <div v-if="activeIdx === i && stage >= 1" class="im-msg">{{ p.msg }}</div>
                <div v-if="activeIdx === i && stage >= 2" class="im-reply">
                  <span class="fbadge ai">AI</span>
                  <span class="im-reply-text">{{ p.reply }}</span>
                </div>
              </div>
            </div>
            <div class="im-arrow" :class="{ live: activeIdx === i && stage >= 1 }">
              <span class="im-arrow-track"></span>
              <span class="im-arrow-particle"></span>
            </div>
          </div>
        </div>

        <!-- Right: Mortgage Work. The agent works behind the scenes. -->
        <div class="work-panel">
          <div class="work-head">
            <span class="console-dots">
              <span class="dot-r"></span><span class="dot-y"></span><span class="dot-g"></span>
            </span>
            <span class="work-title">mortgage work</span>
            <span class="work-via" :class="{ on: activeIdx >= 0 && stage >= 1 }">
              {{ activeIdx >= 0 && stage >= 1 ? 'via ' + platforms[activeIdx].name : 'idle' }}
            </span>
          </div>
          <div class="work-client">
            <span class="fbadge md">CLIENT</span>
            <span class="work-client-name">{{ clientName }}</span>
          </div>
          <div class="work-body">
            <div v-for="(l, i) in visibleLines" :key="i" class="work-line" :class="l.type">
              <span class="wl-box">
                <svg viewBox="0 0 10 10" width="8" height="8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M1.5 5.5 4 8l4.5-6"/>
                </svg>
              </span>
              <span class="wl-text" v-html="l.text"></span>
            </div>
            <div v-if="stage === 1" class="work-line typing">
              <span class="wl-box"></span>
              <span class="wl-cursor"></span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

// One scenario per IM platform: the LO's message, the agent's reply, and the
// steps the agent runs inside Mortgage Work before answering back.
const platforms = [
  {
    id: 'slack',
    mono: 'SL',
    name: 'Slack',
    client: 'sarah-mitchell · Purchase $680K',
    msg: 'Does Sarah qualify for conventional?',
    reply: 'Yes — DTI 30.9%, FICO 742. Conventional works if we get an LOE for the 06/14 deposit.',
    lines: [
      { type: 'sys', text: 'message received via Slack' },
      { type: 'agent', text: 'opening sarah-mitchell · reading income docs' },
      { type: 'agent', text: 'DTI <b>30.9%</b> · LTV 78% · FICO 742' },
      { type: 'done', text: 'reply sent back to Slack · saved to ai/profile.ai' },
    ],
  },
  {
    id: 'feishu',
    mono: 'FE',
    name: 'Feishu',
    client: 'david-park · Refinance $412K',
    msg: 'Lock the rate — 6.375% with no points.',
    reply: 'Locked at 6.375%, 30 days. Confirmation saved to the file.',
    lines: [
      { type: 'sys', text: 'message received via Feishu' },
      { type: 'agent', text: 'checking lock pricing · investor rate sheets' },
      { type: 'agent', text: '6.375% no-points available · 30-day window' },
      { type: 'done', text: 'lock confirmed · reply sent back to Feishu' },
    ],
  },
  {
    id: 'dingtalk',
    mono: 'DT',
    name: 'DingTalk',
    client: 'james-whitfield · Purchase $540K',
    msg: 'Need updated paystubs from the Whitfields.',
    reply: 'Request drafted and sent — due Friday. I\'ll chase if nothing lands by noon.',
    lines: [
      { type: 'sys', text: 'message received via DingTalk' },
      { type: 'agent', text: 'checking file · last paystub is 45 days old' },
      { type: 'agent', text: 'borrower request drafted · due Friday' },
      { type: 'done', text: 'request sent · reply back to DingTalk' },
    ],
  },
  {
    id: 'wecom',
    mono: 'WC',
    name: 'WeCom',
    client: 'linda-hayes · Purchase $465K',
    msg: 'Can we move the Hayes closing to Friday?',
    reply: 'Yes — CD wait clears by then. Title confirmed for Friday 10:00.',
    lines: [
      { type: 'sys', text: 'message received via WeCom' },
      { type: 'agent', text: 'checking closing disclosure · 3-day wait' },
      { type: 'agent', text: 'title company confirmed · Friday 10:00' },
      { type: 'done', text: 'Friday works · reply sent back to WeCom' },
    ],
  },
]

const activeIdx = ref(-1)
// 0 = idle, 1 = message in / agent working, 2 = reply sent back
const stage = ref(0)
const visibleLines = ref([])

const clientName = computed(() =>
  activeIdx.value >= 0 && stage.value >= 1 ? platforms[activeIdx.value].client : '—'
)

let timers = []
const schedule = (fn, ms) => {
  timers.push(setTimeout(fn, ms))
}

const runCycle = () => {
  // Reset the previous platform before the next one lights up.
  visibleLines.value = []
  stage.value = 0
  schedule(() => {
    activeIdx.value = (activeIdx.value + 1) % platforms.length
    stage.value = 1
    const p = platforms[activeIdx.value]
    let li = 0
    const typeLine = () => {
      if (li < p.lines.length) {
        visibleLines.value.push(p.lines[li])
        li++
        schedule(typeLine, 750)
      } else {
        schedule(() => { stage.value = 2 }, 300)
        schedule(runCycle, 3400)
      }
    }
    schedule(typeLine, 500)
  }, 1400)
}

onMounted(() => schedule(runCycle, 700))
onUnmounted(() => timers.forEach(clearTimeout))
</script>
