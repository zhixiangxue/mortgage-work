<template>
  <div class="dl-wrap" :class="{ expanded }">
    <button class="dl-btn" @click="toggle">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
      </svg>
      <span class="dl-label">
        {{ detected ? `Download for ${osLabel}` : 'Download' }}
      </span>
      <svg v-if="!detected" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :class="{ flip: expanded }">
        <path d="m6 9 6 6 6-6"/>
      </svg>
    </button>
    <div v-if="!detected && expanded" class="dl-menu">
      <a v-for="p in platforms" :key="p.os" :href="p.url" class="dl-item">
        <span v-html="p.icon"></span>
        <span>{{ p.label }}</span>
      </a>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const detected = ref(false)
const osLabel = ref('')
const expanded = ref(false)

const base = 'https://github.com/zhixiangxue/mortgage-work/releases/latest'

const platforms = [
  { os: 'mac', label: 'macOS', url: `${base}/download/MortgageWork-mac.dmg`, icon: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3a4 4 0 0 0-4 4 4 4 0 0 1 4-4Z"/><path d="M12 7c0-2 1-4 4-4M12 7c0-2-1-4-4-4"/><rect x="4" y="8" width="16" height="13" rx="1"/></svg>` },
  { os: 'win', label: 'Windows', url: `${base}/download/MortgageSetup.exe`, icon: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="1"/><path d="M3 9h18"/></svg>` },
  { os: 'linux', label: 'Linux', url: `${base}/download/MortgageWork-linux.AppImage`, icon: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 10v4M16 10v4M8 12h8"/></svg>` },
]

const toggle = () => { expanded.value = !expanded.value }

onMounted(() => {
  const ua = navigator.userAgent
  if (/Mac OS X|Macintosh/i.test(ua)) {
    detected.value = true
    osLabel.value = 'macOS'
  } else if (/Windows/i.test(ua)) {
    detected.value = true
    osLabel.value = 'Windows'
  } else if (/Linux/i.test(ua) && !/Android/i.test(ua)) {
    detected.value = true
    osLabel.value = 'Linux'
  }
})
</script>
