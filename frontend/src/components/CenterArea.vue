<script setup>
import DocViewer from "./DocViewer.vue";
import StatusBar from "./StatusBar.vue";
</script>

<template>
  <div id="center">
    <!-- Always the editor — empty state when nothing is open, like a real IDE -->
    <DocViewer />
    <StatusBar />
  </div>
</template>

<style scoped>
#center { flex: 1; min-width: 320px; display: flex; flex-direction: column; background: var(--bg); }
</style>
