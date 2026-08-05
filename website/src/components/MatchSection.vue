<template>
  <section id="match" class="match">
    <div class="shell">
      <div class="section-head">
        <p class="section-eyebrow"><span class="dot"></span> The AI works alongside you</p>
        <h2>Drop everything your clients send.<br>AI handles the rest.</h2>
        <p>
          Paystubs, bank statements, IM screenshots, call recordings — throw it all in.
          The AI reads everything, cross-references against lender guidelines, and tells
          you which products fit — with the exact guideline citation.
        </p>
      </div>

      <!-- The visual equation: inputs → AI → result -->
      <div class="eq-stage">
        <!-- Input column 1 -->
        <div class="eq-input">
          <div class="eq-input-label">BORROWER DOCS</div>
          <div class="eq-stack">
            <div class="eq-chip" v-for="doc in docs" :key="doc.name"
                 :class="{ on: flowStep >= 1 }">
              <span class="fbadge" :class="doc.type">{{ doc.type.toUpperCase() }}</span>
              <span>{{ doc.name }}</span>
            </div>
          </div>
        </div>

        <span class="eq-plus">+</span>

        <!-- Input column 2 -->
        <div class="eq-input">
          <div class="eq-input-label">LENDER PRODUCTS</div>
          <div class="eq-stack">
            <div class="eq-chip" v-for="prod in products" :key="prod.name"
                 :class="{ on: flowStep >= 1 }">
              <span class="fbadge pdf">PDF</span>
              <span>{{ prod.name }}</span>
            </div>
          </div>
        </div>

        <span class="eq-arrow">→</span>

        <!-- AI orb -->
        <div class="match-engine" :class="{ active: flowStep >= 1 }">
          <div class="engine-lines">
            <div class="line-track line-left">
              <span class="line-particle" v-for="n in 3" :key="'l'+n" :style="{ animationDelay: n * 0.5 + 's' }"></span>
            </div>
            <div class="line-track line-right">
              <span class="line-particle" v-for="n in 3" :key="'r'+n" :style="{ animationDelay: n * 0.5 + 's' }"></span>
            </div>
          </div>
          <div class="engine-orb">
            <div class="ring ring-outer"></div>
            <div class="ring ring-mid"></div>
            <div class="ring ring-inner"></div>
            <div class="orb-core">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/>
              </svg>
            </div>
          </div>
          <div class="engine-label">AI MATCH</div>
        </div>

        <span class="eq-arrow">=</span>

        <!-- Result column — always visible; items start as "scanning" then settle -->
        <div class="eq-result">
          <div class="eq-result-label">AI MATCH RESULT</div>
          <div
            class="eq-result-item"
            v-for="(prod, i) in products"
            :key="prod.name"
            :class="itemClass(prod.name, i)"
            :style="{ transitionDelay: i * 0.15 + 's' }"
          >
            <span class="ri-badge" :class="badgeClass(prod.name, i)">{{ badgeText(prod.name, i) }}</span>
            <span class="ri-name">{{ prod.name }}</span>
            <span class="ri-detail">{{ detailText(prod.name, i) }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const docs = [
  { name: 'paystub-2026-07.pdf', type: 'pdf' },
  { name: 'bank-stmt-jun.pdf', type: 'pdf' },
  { name: 'credit-report.pdf', type: 'pdf' },
  { name: 'w2-2025.pdf', type: 'pdf' },
]
const products = [
  { name: 'UWM Conventional', match: true },
  { name: 'A&D Bank Statement', match: true },
  { name: 'Rocket Jumbo', match: false },
  { name: 'FHA 203(b)', match: false },
]

const matchData = {
  'UWM Conventional':   { badge: 'QUALIFIED', cls: 'ok',  detail: 'DTI 30.9% — if $18K deposit LOE clears' },
  'A&D Bank Statement':  { badge: 'QUALIFIED', cls: 'ok',  detail: '80% LTV · min FICO 680 · has 742' },
  'Rocket Jumbo':        { badge: 'DECLINED',  cls: 'bad', detail: 'Max LTV 80% at this loan amount' },
  'FHA 203(b)':          { badge: 'DECLINED',  cls: 'bad', detail: 'Loan amount exceeds FHA limits' },
}

const flowStep = ref(0)

// Step 0: nothing. Step 1: inputs + orb active, results show as "scanning".
// Step 2: results settle one by one into QUALIFIED / DECLINED.
function itemClass(name, i) {
  if (flowStep.value === 0) return 'hidden'
  if (flowStep.value === 1) return 'scanning'
  // flowStep >= 2: settle sequentially — items before the "settle cursor" are decided
  const settled = flowStep.value - 2 // how many items have settled so far
  if (i < settled) {
    return matchData[name].cls === 'ok' ? 'matched' : 'rejected'
  }
  if (i === settled) {
    return matchData[name].cls === 'ok' ? 'matched' : 'rejected'
  }
  return 'scanning'
}
function badgeClass(name, i) {
  const cls = itemClass(name, i)
  if (cls === 'matched') return 'ok'
  if (cls === 'rejected') return 'bad'
  return 'scan'
}
function badgeText(name, i) {
  const cls = itemClass(name, i)
  if (cls === 'matched' || cls === 'rejected') return matchData[name].badge
  return 'SCANNING'
}
function detailText(name, i) {
  const cls = itemClass(name, i)
  if (cls === 'matched' || cls === 'rejected') return matchData[name].detail
  return ''
}

onMounted(() => {
  const cycle = () => {
    flowStep.value = 0
    setTimeout(() => { flowStep.value = 1 }, 600)
    // Settle items one by one: each step beyond 2 settles the next product
    products.forEach((_, i) => {
      setTimeout(() => { flowStep.value = 2 + i }, 2200 + i * 600)
    })
  }
  cycle()
  setInterval(cycle, 7000)
})
</script>
