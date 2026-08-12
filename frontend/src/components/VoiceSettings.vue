<script setup>
/* Voice device settings — connect a recording device by its 6-digit code,
   browse transcriptions pulled from the device, and copy any transcript
   into a client folder via paste.

   Three visual states, same pattern as MemoryViewer:
   A. Not connected — 6-digit code input (auto-connects on completion).
   B. Connecting — brief spinner.
   C. Connected — device header + transcript list with expand/copy.

   All data is mock for now — the real device API and agent tick come later. */
import { ref, computed, nextTick, onMounted } from "vue";
import { store } from "../store.js";

/* ---- state ---------------------------------------------------------------- */
const VALID_CODE = "102938";     // the one demo device code

// 6-digit code input boxes
const code = ref(["", "", "", "", "", ""]);
const codeEls = ref([]);         // DOM refs for focus management
const shaking = ref(false);

// Connection lifecycle
const connected = ref(false);
const connecting = ref(false);
const deviceCode = ref("");      // the code that succeeded

// Transcript list
const expanded = ref(new Set()); // expanded transcript ids
const copiedId = ref("");        // transcript id currently showing the check mark

/* ---- mock transcript data ------------------------------------------------- */
const TRANSCRIPTS = [
  {
    id: "tr_001",
    time: "08/12 2:30 PM",
    full: `[2:32 PM] Thanks for coming in, Michael. I wanted to go over the cash-out refinance numbers we discussed last week.

[2:33 PM] Yeah, absolutely. Sarah and I have been talking about it and we're pretty confident this is the right move.

[2:33 PM] So just to recap — your current balance with Wells Fargo is about $271,000 at 3.75%. The appraisal came back at $520,000, which gives us plenty of equity to work with.

[2:34 PM] Right. And the main thing is those credit cards. We're paying about $2,300 a month just in minimums across three cards.

[2:34 PM] Exactly. So the new loan at $416,000, 6.5% 30-year fixed, pays off the existing mortgage, the $78,000 in credit card debt, and you still walk away with about $51,000 in cash for the kitchen remodel.

[2:36 PM] One thing — the property at 7842 W Desert Cove, do we need a new title commitment?`,
    status: "filed",
    target: "Michael & Sarah Thompson"
  },
  {
    id: "tr_002",
    time: "08/12 10:15 AM",
    full: `[10:15 AM] Hi James, thanks for hopping on the call. I wanted to walk through where we stand on the Cedar Ridge property.

[10:16 AM] Sounds good. Emily's here with me too.

[10:16 AM] So the purchase price is $720,000, we're targeting 80% LTV so the loan amount comes to $576,000. Both of you are W-2 — your base at Vantage Technologies is $215,000 plus about $26K bonus, and Emily you're at $148,000 base at BrightPath.

[10:17 AM] That's right. And we have about $165K in checking and another $285K in the Vanguard brokerage. Plus my dad Robert is gifting $50,000.

[10:19 AM] That's the plan. This will be our first home.`,
    status: "filed",
    target: "James & Emily Whitfield"
  },
  {
    id: "tr_003",
    time: "08/11 4:00 PM",
    full: `[4:00 PM] So I was thinking about the down payment options for the investment property in Miami. We could go with 25% down which gives us better cash flow, or push to 30% for a lower rate.

[4:02 PM] The DSCR numbers work either way, but barely — market rent is $3,200 and the PITIA at 25% down comes to about $2,800. That's a 1.14 ratio. At 30% down it's closer to 1.28 which gives us more cushion.

[4:03 PM] I think we should go 30%. The rate improvement is marginal but the comfort level matters, especially if the property sits vacant for a month between tenants.`,
    status: "new",
    target: null
  },
  {
    id: "tr_004",
    time: "08/10 9:00 AM",
    full: `[9:00 AM] Just a quick note — I talked to the listing agent and they accepted our counteroffer on the Bellevue property. We need to move fast on the appraisal.

[9:01 AM] The purchase price came in at $1.2 million with a $960,000 loan amount at 80% LTV. They wanted to close in 30 days which is tight but doable if we get the appraisal ordered today.

[9:02 AM] I already sent over the credit authorization and the earnest money is wired. Next step is getting the home inspection scheduled for Thursday.`,
    status: "new",
    target: null
  }
];

/* ---- derived state -------------------------------------------------------- */
const isOff    = computed(() => !connected.value && !connecting.value);
const isConn   = computed(() => connecting.value);
const isOn     = computed(() => connected.value);

const codeStr = computed(() => code.value.join(""));
const codeReady = computed(() => codeStr.value.length === 6);

/* ---- code input handlers -------------------------------------------------- */
function onCodeInput(e, idx) {
  // Only allow digits
  e.target.value = e.target.value.replace(/[^0-9]/g, "").slice(0, 1);
  code.value[idx] = e.target.value;
  // Auto-advance to next box
  if (e.target.value && idx < 5) {
    nextTick(() => codeEls.value[idx + 1]?.focus());
  }
  // Auto-submit when all 6 filled
  if (codeStr.value.length === 6) {
    setTimeout(() => {
      if (codeStr.value === VALID_CODE) doConnect();
      else shakeError();
    }, 200);
  }
}

function onCodeKey(e, idx) {
  // Backspace on empty box → jump to previous
  if (e.key === "Backspace" && !code.value[idx] && idx > 0) {
    code.value[idx - 1] = "";
    nextTick(() => codeEls.value[idx - 1]?.focus());
    e.preventDefault();
  }
  // Enter triggers validation if ready
  if (e.key === "Enter" && codeReady.value) {
    if (codeStr.value === VALID_CODE) doConnect();
    else shakeError();
  }
}

function shakeError() {
  shaking.value = true;
  setTimeout(() => {
    code.value = ["", "", "", "", "", ""];
    shaking.value = false;
    nextTick(() => codeEls.value[0]?.focus());
  }, 500);
}

/* ---- connection lifecycle ------------------------------------------------- */
function doConnect() {
  connecting.value = true;
  setTimeout(() => {
    deviceCode.value = codeStr.value;
    connecting.value = false;
    connected.value = true;
    expanded.value.clear();
    copiedId.value = "";
  }, 1500);
}

function disconnect() {
  connected.value = false;
  deviceCode.value = "";
  code.value = ["", "", "", "", "", ""];
  expanded.value.clear();
  copiedId.value = "";
  nextTick(() => codeEls.value[0]?.focus());
}

function refreshList() {
  // No-op for mock data — real implementation would re-fetch from device API
}

/* ---- transcript list ------------------------------------------------------ */
function toggleExpand(id) {
  if (expanded.value.has(id)) expanded.value.delete(id);
  else expanded.value.add(id);
}

async function copyTranscript(t) {
  try {
    await navigator.clipboard.writeText(t.full);
  } catch {
    // Fallback for environments without clipboard API
    const ta = document.createElement("textarea");
    ta.value = t.full;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch { /* ignore */ }
    document.body.removeChild(ta);
  }
  copiedId.value = t.id;
  setTimeout(() => { if (copiedId.value === t.id) copiedId.value = ""; }, 1500);
}

/* Focus the first code box on mount when not connected */
onMounted(() => {
  if (!connected.value) nextTick(() => codeEls.value[0]?.focus());
});
</script>

<template>
  <div class="viewer" :class="{ connected: isOn }">

    <!-- ===== A. Not connected ===== -->
    <div v-if="isOff" class="empty-state">
      <div class="e-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
          <line x1="12" y1="19" x2="12" y2="23"/>
          <line x1="8" y1="23" x2="16" y2="23"/>
        </svg>
      </div>
      <div class="e-title">No voice device connected</div>
      <div class="e-sub">Enter the 6-digit code on your device to connect.</div>
      <div class="code-boxes" :class="{ shaking }">
        <input
          v-for="(_, i) in code" :key="i"
          :ref="el => codeEls[i] = el"
          class="code-box"
          :class="{ filled: code[i], error: shaking }"
          type="text"
          maxlength="1"
          inputmode="numeric"
          :value="code[i]"
          @input="onCodeInput($event, i)"
          @keydown="onCodeKey($event, i)"
        />
      </div>
    </div>

    <!-- ===== B. Connecting ===== -->
    <div v-else-if="isConn" class="connecting">
      <div class="fb-spin"></div>
      Connecting to device…
    </div>

    <!-- ===== C. Connected ===== -->
    <template v-else-if="isOn">

      <!-- Device header -->
      <div class="device-header">
        <div class="device-info">
          <span class="device-url">Device · {{ deviceCode }}</span>
          <span class="status-tag"><span class="dot"></span>Connected</span>
        </div>
        <div class="device-actions">
          <button class="action-btn" @click="refreshList()">Refresh</button>
          <button class="action-btn danger" @click="disconnect()">Disconnect</button>
        </div>
      </div>

      <!-- Transcript list -->
      <div class="transcript-list">
        <div class="list-header">
          <span>{{ TRANSCRIPTS.length }} recordings</span>
        </div>
        <div v-for="t in TRANSCRIPTS" :key="t.id" class="t-card">
          <div class="t-card-body">
            <div class="t-card-meta">
              <span class="t-card-time">{{ t.time }}</span>
              <span class="t-status" :class="t.status">{{ t.status === 'filed' ? 'Auto-filed' : 'New' }}</span>
            </div>
            <div class="t-card-preview" :class="{ expanded: expanded.has(t.id) }" @click="toggleExpand(t.id)">{{ t.full }}</div>
            <div class="t-card-chevron" @click="toggleExpand(t.id)">
              {{ expanded.has(t.id) ? '▴ show less' : '▾ show more' }}
            </div>
            <div v-if="t.target" class="t-status-target">Filed under {{ t.target }}</div>
          </div>
          <button class="t-copy" :class="{ copied: copiedId === t.id }" title="Copy transcript" @click="copyTranscript(t)">
            <svg v-if="copiedId !== t.id" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 12 10 18 20 6"/></svg>
          </button>
        </div>
      </div>

    </template>

  </div>
</template>

<style scoped>
/* height: 100% so the viewer fills .settings-content even though that
   container is not itself a flex parent — this lets the connecting and
   empty states centre vertically instead of snapping to the top. */
.viewer { height: 100%; display: flex; flex-direction: column; overflow: hidden; }
.viewer.connected { background: var(--bg-editor); }

/* ---- Empty state ---- */
.empty-state {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 40px; text-align: center;
}
.e-icon { color: var(--text-4); margin-bottom: 16px; }
.e-icon svg { width: 40px; height: 40px; }
.e-title { font: 600 15px var(--sans); color: var(--text-2); margin-bottom: 6px; }
.e-sub { font: 400 12px var(--sans); color: var(--text-4); max-width: 360px; line-height: 1.6; }

/* ---- 6-digit code input ---- */
.code-boxes {
  display: flex; gap: 10px; margin-top: 20px;
}
.code-boxes.shaking { animation: shake .4s ease-out; }
.code-box {
  width: 48px; height: 56px;
  background: var(--bg-hover); border: 1px solid var(--border);
  color: var(--text); font: 600 22px var(--mono);
  text-align: center; outline: none;
  transition: border-color .15s;
}
.code-box:focus { border-color: var(--brand); }
.code-box.filled { border-color: var(--border-soft); }
.code-box.error { border-color: var(--red); }
@keyframes shake {
  10%, 90% { transform: translateX(-2px); }
  20%, 80% { transform: translateX(3px); }
  30%, 50%, 70% { transform: translateX(-5px); }
  40%, 60% { transform: translateX(5px); }
}

/* ---- Connecting ---- */
.connecting {
  flex: 1; display: flex; align-items: center; justify-content: center;
  gap: 10px; color: var(--text-3); font-size: 13px;
}
.fb-spin {
  width: 16px; height: 16px; border-radius: 50%;
  border: 2px solid var(--border); border-top-color: var(--brand);
  animation: fb-rot .7s linear infinite;
}
@keyframes fb-rot { to { transform: rotate(360deg); } }

/* ---- Device header ---- */
.device-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
}
.device-info { display: flex; align-items: center; gap: 10px; }
.device-url { font: 400 11px var(--mono); color: var(--text-4); }
.status-tag {
  display: inline-flex; align-items: center; gap: 5px;
  font: 600 10px var(--mono);
  padding: 3px 8px;
  background: var(--tint-green); color: var(--green);
}
.status-tag .dot { width: 5px; height: 5px; background: var(--green); border-radius: 50%; }
.device-actions { display: flex; gap: 12px; align-items: center; }
.action-btn {
  font: 400 11px var(--mono);
  padding: 5px 12px;
  background: var(--bg-raise); border: 1px solid var(--border-soft);
  color: var(--text-3); cursor: pointer;
  transition: all .12s;
}
.action-btn:hover { color: var(--text-2); border-color: var(--text-4); }
.action-btn.danger:hover { color: var(--red); border-color: rgba(235,54,28,.3); }

/* ---- Transcript list ---- */
/* overflow-y: scroll (not auto) so the 8px gutter is always reserved —
   the transparent track means it's invisible when there's nothing to
   scroll, but the content width never jumps when a scrollbar appears. */
.transcript-list { flex: 1; overflow-y: scroll; padding: 8px 20px; }
.list-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 0 8px;
  font: 400 11px var(--mono); color: var(--text-4);
}
.t-card {
  padding: 12px 14px;
  background: var(--bg-panel); border: 1px solid var(--border);
  margin-bottom: 6px;
  display: flex; align-items: flex-start; gap: 12px;
  transition: border-color .15s;
}
.t-card:hover { border-color: var(--border-soft); }
.t-card-body { flex: 1; min-width: 0; }
.t-card-meta {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 4px;
}
.t-card-time { font: 400 10.5px var(--mono); color: var(--text-4); }

/* Status badges — inline with timestamp */
.t-status {
  font: 600 9.5px var(--mono);
  padding: 2px 6px;
  letter-spacing: .03em;
}
.t-status.filed { background: var(--tint-green); color: var(--green); }
.t-status.new { background: var(--tint-amber); color: var(--amber); }
.t-status-target {
  font: 400 10px var(--sans); color: var(--text-3);
  margin-top: 4px;
}

/* Transcript preview / expand */
.t-card-preview {
  font: 400 12.5px var(--sans); color: var(--text-2);
  line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
  overflow: hidden; cursor: pointer;
}
.t-card-preview.expanded {
  -webkit-line-clamp: unset;
  white-space: pre-wrap;
}
.t-card-chevron {
  font: 400 10px var(--mono); color: var(--text-4);
  margin-top: 4px; cursor: pointer;
  display: inline-flex; align-items: center; gap: 3px;
  user-select: none;
}
.t-card-chevron:hover { color: var(--text-2); }

/* Copy icon — always visible, quiet until hovered */
.t-copy {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  background: none; border: 1px solid transparent;
  color: var(--text-4); cursor: pointer;
  flex-shrink: 0;
  transition: color .12s, border-color .12s, background .12s;
}
.t-copy:hover {
  color: var(--text-2); border-color: var(--border-soft);
  background: var(--bg-hover);
}
.t-copy.copied { color: var(--brand); border-color: rgba(60,215,66,.2); }
.t-copy svg { width: 14px; height: 14px; }
</style>
