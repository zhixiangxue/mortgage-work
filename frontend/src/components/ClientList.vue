<script setup>
import { ref } from "vue";
import { store, openClient, openNewClient, openClientListCtx, refreshWorkspace, CLIENT_MIME, showToast } from "../store.js";

const blockedDrop = ref(false);
const refreshing = ref(false);

// Refresh spins while the snapshot loads; a minimum visible duration keeps
// the feedback perceptible when the backend answers instantly.
async function onRefresh() {
  if (refreshing.value) return;
  refreshing.value = true;
  const t0 = Date.now();
  await refreshWorkspace();
  const left = 400 - (Date.now() - t0);
  if (left > 0) await new Promise(r => setTimeout(r, left));
  refreshing.value = false;
}

function isOsFileDrag(e) {
  return e.dataTransfer && e.dataTransfer.types && e.dataTransfer.types.includes("Files");
}

function onDragOver(e) {
  if (!isOsFileDrag(e)) return;
  e.preventDefault();
  e.stopPropagation();
  e.dataTransfer.dropEffect = "none";
  blockedDrop.value = true;
}

function onDragLeave(e) {
  if (!e.currentTarget.contains(e.relatedTarget)) blockedDrop.value = false;
}

function onDrop(e) {
  if (!isOsFileDrag(e)) return;
  e.preventDefault();
  e.stopPropagation();
  blockedDrop.value = false;
  showToast("Open a client first, then drop files into its folders");
}

// A client row drags as a whole folder: CLIENT_MIME carries the identity for
// the chat composer; text/plain (with the dir slash) keeps any plain-text
// target sensible. No TREE_MIME — a client is not movable inside a tree.
function dragClient(e, c) {
  e.dataTransfer.setData("text/plain", c.id + "/");
  e.dataTransfer.setData(CLIENT_MIME, JSON.stringify({ id: c.id, name: c.name }));
}
</script>

<template>
  <div class="wrap">
    <div class="panel-header">
      Clients
      <span class="icons">
        <span class="hic" data-tip="New client" @click="openNewClient()">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M12 5v14M5 12h14"/>
          </svg>
        </span>
        <span class="hic" :class="{ spinning: refreshing }" data-tip="Refresh" @click="onRefresh()">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12a9 9 0 1 1-2.64-6.36"/>
            <polyline points="21 3 21 9 15 9"/>
          </svg>
        </span>
      </span>
    </div>
    <div id="side-clients" :class="{ 'blocked-drop': blockedDrop }"
         @contextmenu.prevent="openClientListCtx($event)"
         @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop">
      <!-- Empty book of business: explain the two ways clients arrive instead
           of a blank gap. Same quiet tone as the Tools panel empty state. -->
      <div v-if="!store.clients.length && !store.closed.length" class="empty">
        <div class="e-icon">
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="8.5" cy="7" r="4"/>
            <path d="M20 8v6M23 11h-6"/>
          </svg>
        </div>
        <div class="e-title">No clients yet</div>
        <div class="e-sub">Start your book — create a client, then drop documents into that client's folders.</div>
        <button class="e-btn" @click="openNewClient()">New client →</button>
      </div>
      <div v-for="c in store.clients.concat(store.closed)" :key="c.id"
           class="client-row" :class="{ selected: store.client && store.client.id === c.id }"
           draggable="true" @dragstart="dragClient($event, c)"
           @click="openClient(c.id)"
           @contextmenu.prevent.stop="openClientListCtx($event, c.id)">
        <div class="cname">{{ c.name }}<span class="when">{{ c.touched }}</span></div>
        <div class="cpurpose">{{ c.purpose }} · <span class="amt">{{ c.amount }}</span></div>
        <div class="cmeta">
          <span class="stage" :class="c.stage">{{ c.stageLbl }}</span>
          <span v-if="c.missing" class="miss">{{ c.missing }} missing</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; flex: 1; min-height: 0; }
/* Refresh feedback: spin the glyph until the snapshot lands */
.hic.spinning svg { animation: hic-spin .7s linear infinite; }
@keyframes hic-spin { to { transform: rotate(360deg); } }
#side-clients { flex: 1; overflow-y: auto; display: flex; flex-direction: column; position: relative; }
#side-clients.blocked-drop { outline: 1px dashed var(--red); outline-offset: -6px; }
#side-clients.blocked-drop::after {
  content: "Open a client first, then drop files into its folders";
  position: absolute; inset: 8px; z-index: 5; pointer-events: none;
  display: flex; align-items: center; justify-content: center; text-align: center;
  padding: 18px; background: color-mix(in srgb, var(--tint-red) 82%, transparent);
  border: 1px dashed var(--red); color: var(--red);
  font: 500 11px var(--mono); line-height: 1.5;
}
/* Empty state — same vocabulary as the Tools panel: dim icon, two lines of
   plain-language guidance, one clear action */
.empty {
  display: flex; flex-direction: column; align-items: center;
  gap: 8px; padding: 40px 20px 20px; user-select: none;
}
.e-icon { color: var(--text-4); opacity: .4; margin-bottom: 6px; }
.e-title { font: 600 12px var(--mono); color: var(--text-3); }
.e-sub { font: 400 10.5px var(--mono); color: var(--text-4); text-align: center; line-height: 1.5; }
.e-btn {
  margin-top: 10px; cursor: pointer;
  font: 500 10.5px var(--mono); color: var(--text-2);
  background: var(--bg-panel); border: 1px solid var(--border);
  padding: 6px 16px; transition: border-color .15s, color .15s;
}
.e-btn:hover { border-color: var(--brand); color: var(--brand); }
.client-row {
  padding: 12px 14px 13px; cursor: pointer;
  border-bottom: 1px solid var(--bg-panel);
}
.client-row:hover { background: var(--bg-hover); }
.client-row.selected { background: var(--bg-raise); box-shadow: inset 2px 0 0 var(--brand); }
/* Line 1: who + last touch (top-right, mail-client style) */
.client-row .cname {
  font: 600 13px var(--sans); color: var(--text-2);
  display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
}
.client-row:hover .cname { color: var(--text); }
.client-row .when { font: 400 9.5px var(--mono); color: var(--text-4); flex-shrink: 0; }
/* Line 2: purpose + amount — same triage line as the welcome cards */
.client-row .cpurpose { margin-top: 5px; font: 400 10px var(--mono); color: var(--text-4); }
.client-row .cpurpose .amt { color: var(--text-3); }
/* Line 3: where it's stuck */
.client-row .cmeta { margin-top: 8px; font: 400 10px var(--mono); color: var(--text-4); display: flex; gap: 8px; align-items: center; }
</style>
