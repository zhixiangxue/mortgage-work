<template>
  <section id="skills" class="skills">
    <div class="shell">
      <div class="section-head">
        <p class="section-eyebrow"><span class="dot"></span> Your agent gets smarter with every skill</p>
        <h2>A growing library of mortgage skills.</h2>
        <p>
          Skills are specialized capabilities the agent uses to do real loan-officer work —
          from DTI calculation to fraud detection. Add the ones you need; the agent
          learns your workflow.
        </p>
      </div>

      <div class="skill-grid">
        <div class="skill-card" v-for="(s, i) in skills" :key="s.name"
             :style="{ animationDelay: i * 0.08 + 's' }"
             @mouseenter="hovered = i" @mouseleave="hovered = -1"
             :class="{ hovered: hovered === i }">
          <span class="skill-svg" v-html="s.svg"></span>
          <span class="skill-name">{{ s.name }}</span>
          <span class="skill-desc">{{ s.desc }}</span>
          <span class="skill-tag">{{ s.tag }}</span>
        </div>

        <!-- More skills teaser card -->
        <div class="skill-card skill-more" @mouseenter="hovered = skills.length" @mouseleave="hovered = -1"
             :class="{ hovered: hovered === skills.length }">
          <span class="more-num">1,000<span class="more-plus">+</span></span>
          <span class="more-label">mortgage tools & integrations</span>
          <span class="more-sub">via open skill marketplace</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'

const hovered = ref(-1)

// Outline-style SVGs, 24x24, stroke=currentColor — inherit the brand green
const ic = (paths) => `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`

const skills = [
  { svg: ic('<rect x="3" y="14" width="4" height="7"/><rect x="10" y="9" width="4" height="12"/><rect x="17" y="4" width="4" height="17"/>'), name: 'DTI Calculator', desc: 'Front & back ratio from any income structure', tag: 'CORE' },
  { svg: ic('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9 13h6M9 17h4"/>'), name: '1003 Auto-Fill', desc: 'Populate URLA fields from source documents', tag: 'CORE' },
  { svg: ic('<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>'), name: 'Guideline Match', desc: 'Cross-check borrower vs. lender matrix', tag: 'CORE' },
  { svg: ic('<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>'), name: 'Missing Docs', desc: 'Checklist from file contents vs. loan type', tag: 'CORE' },
  { svg: ic('<path d="M3 21h18"/><path d="M3 10h18"/><path d="M5 6l7-3 7 3"/><path d="M4 10v11"/><path d="M20 10v11"/><path d="M8 14v3"/><path d="M12 14v3"/><path d="M16 14v3"/>'), name: 'Bank Statement Analysis', desc: '12-mo average, expense factor, deposit flags', tag: 'NON-QM' },
  { svg: ic('<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>'), name: 'Fraud Signals', desc: 'Flag inconsistent employers, altered docs', tag: 'QC' },
  { svg: ic('<path d="M3 3v18h18"/><path d="m7 14 4-4 4 4 5-6"/>'), name: 'Rate Sheet Reader', desc: 'Parse daily rate sheets into comparable quotes', tag: 'PRICING' },
]
</script>
