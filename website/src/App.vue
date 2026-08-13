<template>
  <ArchitecturePage v-if="view === 'architecture'" @navigate="go" />
  <template v-else>
    <div class="hero-region">
      <SiteHeader />
      <HeroSection />
    </div>
    <main>
      <MatchSection />
      <ChatSection />
      <ProactiveSection />
      <CaptureSection />
      <PipelineSection />
      <AiAnalysisSection />
      <AutoFillSection />
      <SkillsSection />
      <ModelSection />
      <FeatureGrid />
      <FinalCta />
    </main>
    <SiteFooter />
  </template>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import SiteHeader from './components/SiteHeader.vue'
import HeroSection from './components/HeroSection.vue'
import MatchSection from './components/MatchSection.vue'
import ChatSection from './components/ChatSection.vue'
import ProactiveSection from './components/ProactiveSection.vue'
import CaptureSection from './components/CaptureSection.vue'
import PipelineSection from './components/PipelineSection.vue'
import AiAnalysisSection from './components/AiAnalysisSection.vue'
import AutoFillSection from './components/AutoFillSection.vue'
import SkillsSection from './components/SkillsSection.vue'
import ModelSection from './components/ModelSection.vue'
import FeatureGrid from './components/FeatureGrid.vue'
import FinalCta from './components/FinalCta.vue'
import SiteFooter from './components/SiteFooter.vue'
import ArchitecturePage from './components/ArchitecturePage.vue'

const view = ref('home')

function syncFromHash() {
  view.value = window.location.hash === '#architecture' ? 'architecture' : 'home'
}

function go(name) {
  if (name === 'home') {
    window.location.hash = ''
    view.value = 'home'
  } else {
    window.location.hash = name
    view.value = name
  }
  // Scroll to top on view change
  window.scrollTo(0, 0)
}

onMounted(() => {
  syncFromHash()
  window.addEventListener('hashchange', syncFromHash)
})

onUnmounted(() => {
  window.removeEventListener('hashchange', syncFromHash)
})
</script>
