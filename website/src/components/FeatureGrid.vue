<template>
  <section id="features" class="features">
    <div class="shell">
      <div class="section-head">
        <p class="section-eyebrow"><span class="dot"></span> Built for how loan officers actually work</p>
        <h2>Less paperwork. More closings.</h2>
      </div>

      <div class="feature-grid">
        <div class="feature-card" v-for="f in features" :key="f.kicker">
          <span class="fk">{{ f.kicker }}</span>
          <h3>{{ f.title }}</h3>
          <p>{{ f.body }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
const features = [
  {
    kicker: '01 — Organize',
    title: 'Every borrower file in one folder.',
    body: 'Drop paystubs, bank statements, credit reports, even screenshots and call transcripts — organize them however you like. The AI finds what it needs.',
  },
  {
    kicker: '02 — Analyze',
    title: 'AI reads the docs and writes the analysis.',
    body: 'Qualifying income, DTI ratios, document checklists, guideline cross-checks — generated automatically and saved next to the borrower file.',
  },
  {
    kicker: '03 — Close',
    title: 'Never miss a condition again.',
    body: 'The AI tracks what you have, what you need, and what is about to expire. Ask it anything about any borrower, any time, in plain English.',
  },
]
</script>
