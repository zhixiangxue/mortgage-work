<template>
  <section class="hero">
    <div class="shell">
      <div class="hero-copy">
        <p class="hero-eyebrow"><span class="dot"></span> AI workbench for loan officers</p>
        <h1>
          <span class="hero-line">Close loans</span>
          <span class="drop-clip">
            <Transition name="drop" mode="out-in">
              <span :key="current" class="drop-chip">{{ phrases[current] }}</span>
            </Transition>
          </span>
        </h1>
        <p class="lede">
          Borrower docs, lender guidelines, credit reports — drop it all in.
          The AI reads everything, matches products, and gets you to
          clear-to-close before lunch.
        </p>
        <div class="hero-actions">
          <DownloadButton />
        </div>
        <p class="hero-sub">Starts from free &middot; No credit card &middot; Open source &middot; BYOK</p>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import DownloadButton from './DownloadButton.vue'

const phrases = [
  'in minutes, not days.',
  'without the grunt work.',
  'minus the paperwork.',
  'with every guideline checked.',
]

const current = ref(0)
let timer = null

onMounted(() => {
  timer = setInterval(() => {
    current.value = (current.value + 1) % phrases.length
  }, 2600)
})
onUnmounted(() => clearInterval(timer))
</script>
