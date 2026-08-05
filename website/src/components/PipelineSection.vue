<template>
  <section id="pipeline" class="pipeline">
    <div class="shell">
      <div class="section-head">
        <p class="section-eyebrow"><span class="dot"></span> Your pipeline, at a glance</p>
        <h2>Every borrower in one place.</h2>
        <p>
          See who needs docs, who's pre-approved, and who's ready to close — the same
          way you triage your inbox, not buried in a LOS dashboard.
        </p>
      </div>

      <div class="pipeline-demo">
        <div class="mock-panel-header" style="border-bottom:1px solid var(--border)">
          Clients · 4 active
        </div>
        <div class="pipeline-clients">
          <div class="pc-card" v-for="c in clients" :key="c.id">
            <div class="pcn">{{ c.name }}</div>
            <div class="pcp">{{ c.purpose }} · {{ c.amount }}</div>
            <div class="pcs">
              <span class="stage" :class="c.stage">{{ c.stageLbl }}</span>
              <span v-if="c.missing" class="miss">{{ c.missing }} missing</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
// Same client data as the real app's mock (frontend/src/mocks/clients.js)
const clients = [
  { id: 'sarah', name: 'Sarah Mitchell', purpose: 'Purchase', amount: '$680,000', stage: 'docs', stageLbl: 'Collecting Docs', missing: 3 },
  { id: 'james', name: 'James & Amy Chen', purpose: 'Purchase', amount: '$1,150,000', stage: 'active', stageLbl: 'Pre-Approved', missing: 0 },
  { id: 'robert', name: 'Robert Alvarez', purpose: 'Refinance', amount: '$412,000', stage: 'docs', stageLbl: 'Collecting Docs', missing: 5 },
  { id: 'nina', name: 'Nina Petrova', purpose: 'Cash-out Refi', amount: '$520,000', stage: 'lead', stageLbl: 'New Lead', missing: 0 },
]
</script>
