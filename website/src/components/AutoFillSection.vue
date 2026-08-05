<template>
  <section id="autofill" class="autofill">
    <div class="shell">
      <div class="section-head">
        <p class="section-eyebrow"><span class="dot"></span> From documents to forms — automatically</p>
        <h2>The AI fills the paperwork for you.</h2>
        <p>
          Drop the source documents into the borrower folder. The AI extracts the data,
          populates 1003, pre-approval letters, income worksheets, and more — field by field.
          No more copy-pasting from paystubs.
        </p>
      </div>

      <div class="autofill-stage">
        <!-- Left: source docs feeding in -->
        <div class="af-sources">
          <div class="af-source-label">SOURCE DOCUMENTS</div>
          <div class="af-source" v-for="(s, i) in sources" :key="s.name"
               :class="{ read: fillIdx > i }"
               :style="{ transitionDelay: i * 0.15 + 's' }">
            <span class="fbadge" :class="s.type">{{ s.type.toUpperCase() }}</span>
            <span>{{ s.name }}</span>
            <span v-if="fillIdx > i" class="ok">✓</span>
          </div>
        </div>

        <!-- Right: 1003 form filling -->
        <div class="af-form">
          <div class="af-form-header">
            <span class="fbadge pdf">FORM</span>
            URLA / Form 1003 — Draft
            <span class="af-progress">{{ filledCount }}/{{ fields.length }} filled</span>
          </div>
          <div class="af-fields">
            <div class="af-field" v-for="(f, i) in fields" :key="f.label"
                 :class="{ filled: fillIdx > i }"
                 :style="{ transitionDelay: i * 0.15 + 's' }">
              <span class="af-label">{{ f.label }}</span>
              <span class="af-value">{{ fillIdx > i ? f.value : '—' }}</span>
              <span class="af-src" v-if="fillIdx > i">← {{ f.src }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const sources = [
  { name: '1003-application.pdf', type: 'pdf' },
  { name: 'paystub-2026-07.pdf', type: 'pdf' },
  { name: 'bank-stmt-jul.pdf', type: 'pdf' },
  { name: 'credit-report.pdf', type: 'pdf' },
]

const fields = [
  { label: 'Borrower Name', value: 'Sarah Mitchell', src: '1003-application' },
  { label: 'Base Income (Monthly)', value: '$8,200.00', src: 'paystub-07' },
  { label: 'Employer', value: 'ACME Design Co.', src: 'paystub-07' },
  { label: 'Assets — Checking', value: '$47,320', src: 'bank-stmt-jul' },
  { label: 'Credit Score', value: '742 (mid)', src: 'credit-report' },
  { label: 'Loan Amount', value: '$680,000', src: '1003-application' },
]

const fillIdx = ref(0)
const filledCount = computed(() => Math.min(fillIdx.value, fields.length))

onMounted(() => {
  const cycle = () => {
    fillIdx.value = 0
    // Advance one field every 400ms
    const total = sources.length + 1
    for (let i = 1; i <= total; i++) {
      setTimeout(() => { fillIdx.value = i }, i * 400)
    }
  }
  setTimeout(cycle, 500)
  setInterval(cycle, 6500)
})
</script>
