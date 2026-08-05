<template>
  <section id="chat" class="chat-sec">
    <div class="shell">
      <div class="section-head">
        <p class="section-eyebrow"><span class="dot"></span> You're still in the driver's seat</p>
        <h2>Talk to the AI like a colleague.</h2>
        <p>
          The AI does the heavy lifting — reading docs, running numbers, checking guidelines —
          but every decision is yours. Ask follow-up questions, request alternatives,
          or tell it to draft an email. It's a conversation, not a black box.
        </p>
      </div>

      <div class="chat-demo">
        <div class="chat-thread">
          <div class="chat-header">
            <span class="fbadge ai">AI</span>
            <span class="chat-title">Sarah Mitchell — Purchase $680K</span>
          </div>
          <div class="chat-body" ref="body">
            <div
              class="cm"
              v-for="(msg, i) in visible"
              :key="i"
              :class="msg.role"
              :style="{ animationDelay: i * 0.15 + 's' }"
            >
              <span v-if="msg.role === 'user'" class="cm-attach" v-for="p in msg.pills" :key="p">
                <span class="fbadge pdf">PDF</span> {{ p }}
              </span>
              <span class="cm-text" v-html="msg.text"></span>
              <span v-if="msg.role === 'ai' && msg.actions" class="cm-actions">
                <span class="cm-act" v-for="a in msg.actions" :key="a">{{ a }}</span>
              </span>
            </div>
            <div v-if="typing" class="cm ai">
              <span class="cm-typing"><span></span><span></span><span></span></span>
            </div>
          </div>
          <div class="chat-composer">
            <span class="chat-placeholder">Ask about this client, or drop a file…</span>
            <span class="chat-send">↑</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'

const body = ref(null)
const visibleCount = ref(0)
const typing = ref(false)

const conversation = [
  {
    role: 'user',
    pills: ['paystub-07.pdf', 'bank-stmt-jul.pdf'],
    text: 'Does Sarah qualify for conventional, or do we need bank-statement?',
  },
  {
    role: 'ai',
    text: 'DTI is <b>30.9%</b> — under the 43% cap. Conventional works <i>if</i> the <b>$18,000 deposit on 06/14</b> gets an LOE.<br><br>Without the LOE, A&amp;D Bank Statement (Non-QM) qualifies at 80% LTV with no LOE needed — she has a 742 FICO, min is 680.',
    actions: ['Open income analysis', 'Draft LOE request'],
  },
  {
    role: 'user',
    pills: [],
    text: 'What if the co-borrower\'s base salary drops next year?',
  },
  {
    role: 'ai',
    text: 'The co-borrower\'s W-2 base is <b>$98,400/yr</b> — 24 months stable. Even a 15% drop to ~$83.6K keeps total qualifying income at ~$17.8K/mo, front ratio ~24.6%. Still clears.<br><br>The bigger risk is Sarah\'s self-employment income (50% expense factor). If business deposits drop 10%, qualifying drops to ~$18.7K/mo — still OK at 33.6% back ratio.',
  },
]

const visible = computed(() => conversation.slice(0, visibleCount.value))

onMounted(() => {
  const reveal = () => {
    visibleCount.value = 0
    typing.value = false
    const step = () => {
      if (visibleCount.value < conversation.length) {
        typing.value = true
        setTimeout(() => {
          typing.value = false
          visibleCount.value++
          if (visibleCount.value < conversation.length) {
            setTimeout(step, 800)
          }
        }, 1200)
      }
    }
    setTimeout(step, 500)
  }
  reveal()
  setInterval(reveal, 12000)
})

watch(visibleCount, async () => {
  await nextTick()
  if (body.value) body.value.scrollTop = body.value.scrollHeight
})
</script>
