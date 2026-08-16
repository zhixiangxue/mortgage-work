<template>
  <div class="dl-wrap">
    <a class="dl-btn" :href="href" @click.prevent="download">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
      </svg>
      <span class="dl-label">{{ busy ? 'Checking latest version…' : 'Download for Windows' }}</span>
    </a>
    <!-- Per-platform note: mac/Linux visitors are told their version is not out yet. -->
    <div v-if="noteText" class="dl-note">{{ noteText }}</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { DOWNLOAD_URL, resolveDownloadUrl } from '../download.js'

// href starts at the newest release so the button works without JS;
// clicking probes OSS and falls back to an older release if needed.
const href = ref(DOWNLOAD_URL)
const busy = ref(false)

async function download() {
  if (busy.value) return
  busy.value = true
  try {
    href.value = await resolveDownloadUrl()
  } finally {
    busy.value = false
  }
  window.location.href = href.value
}

// Empty for Windows visitors (no note shown).
const noteText = ref('')

onMounted(() => {
  const ua = navigator.userAgent
  if (/Mac OS X|Macintosh/i.test(ua)) {
    noteText.value = 'macOS version coming soon — Windows only for now'
  } else if (/Linux/i.test(ua) && !/Android/i.test(ua)) {
    noteText.value = 'Linux version coming soon — Windows only for now'
  }
})
</script>
