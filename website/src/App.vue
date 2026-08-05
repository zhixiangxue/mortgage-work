<template>
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

<script setup>
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
</script>
