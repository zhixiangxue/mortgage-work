<template>
  <div class="dl-wrap" :class="{ open }" ref="wrapRef">
    <!-- href holds the newest Windows release so the button still downloads
         something sensible with JS disabled; with JS on, clicking just
         toggles the platform menu. -->
    <a class="dl-btn" :href="href" @click.prevent="open = !open">
      <!-- Icon slot: the download arrow and the busy spinner overlap in
           the same 16px box and cross-fade — swapping DOM nodes instead
           would twitch the button. -->
      <span class="dl-icon">
        <svg class="dl-icon-download" :class="{ dim: busy }" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
        </svg>
        <svg class="dl-icon-spinner" :class="{ on: busy }" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
        </svg>
      </span>
      <span class="dl-label">Download for Free</span>
      <svg class="dl-chevron" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6 9l6 6 6-6"/>
      </svg>
    </a>
    <!-- Visitors pick their own platform — no UA guessing. -->
    <ul v-if="open" class="dl-menu">
      <li v-for="p in PLATFORMS" :key="p.id">
        <a href="#" @click.prevent="download(p.id)">
          <!-- Windows logo -->
          <svg v-if="p.icon === 'windows'" viewBox="0 0 448 512" width="14" height="14" fill="currentColor">
            <path d="M0 93.7l183.6-25.3v177.4H0V93.7zm0 324.6l183.6 25.3V268.4H0v149.9zm203.8 28L448 480V268.4H203.8v177.9zm0-380.6v177.4H448V0L203.8 35.7z"/>
          </svg>
          <!-- Apple logo -->
          <svg v-else viewBox="0 0 384 512" width="14" height="14" fill="currentColor">
            <path d="M318.7 268.7c-.2-36.7 16.4-64.4 50-84.8-18.8-26.9-47.2-41.7-84.7-44.6-35.5-2.8-74.3 20.7-88.5 20.7-15 0-49.4-19.7-76.4-19.7C63.3 141.2 4 184.8 4 273.5q0 39.3 14.4 81.2c12.8 36.7 59 126.7 107.2 125.2 25.2-.6 43-17.9 75.8-17.9 31.8 0 48.3 17.9 76.4 17.9 48.6-.7 90.4-82.5 102.6-119.3-65.2-30.7-61.7-90-61.7-91.9zm-56.6-164.2c27.3-32.4 24.8-61.9 24-72.5-24.1 1.4-52 16.4-67.9 34.9-17.5 19.8-27.8 44.3-25.6 71.9 26.1 2 49.9-11.4 69.5-34.3z"/>
          </svg>
          <span class="dl-menu-name">{{ p.label }}</span>
          <span class="dl-menu-detail">{{ p.detail }}</span>
        </a>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { DOWNLOAD_URL, PLATFORMS, getDownloadUrl, preloadDownloadUrls } from '../download.js'

const open = ref(false)
const busy = ref(false)
const href = ref(DOWNLOAD_URL)
const wrapRef = ref(null)

// Close the menu on any click outside of it.
function onDocClick(e) {
  if (wrapRef.value && !wrapRef.value.contains(e.target)) open.value = false
}
onMounted(() => {
  document.addEventListener('click', onDocClick)
  // Warm the HEAD probes in the background so clicks never wait on them.
  preloadDownloadUrls()
})
onUnmounted(() => document.removeEventListener('click', onDocClick))

// Picking a platform uses the pre-probed URL (cached since page load,
// falling back to an older release if the newest is missing) and starts
// the download.
async function download(id) {
  if (busy.value) return
  open.value = false
  busy.value = true
  try {
    href.value = await getDownloadUrl(id) // cached — resolves instantly
    triggerDownload(href.value)
    // The browser still takes a beat to receive headers and open its save
    // dialog; keep the spinner alive across that gap instead of dropping
    // the feedback the moment the URL is handed over.
    await new Promise((r) => setTimeout(r, 1500))
  } finally {
    busy.value = false
  }
}

// A synthetic <a download> click goes down the browser's native download
// path; location.href is treated as a page navigation first, which adds a
// visible "is this a page?" pause before the save dialog appears.
function triggerDownload(url) {
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
}
</script>
