<script setup>
/* Plan — the single home for subscription management. Today: the current
   tier and the redemption-code upgrade. Tomorrow: downgrades, billing
   cycles and whatever else plan changes grow into — all of it lands here.

   Upgrade UI is never embedded inline anywhere else in the app: the
   Knowledge panel's guide card, the account menu, any future entry point
   all just open this tab via openPlan(). */
import { ref, computed, nextTick } from "vue";
import { store } from "../store.js";

const onPro = computed(() => store.plan === "pro");

/* Second step happens in place: the Subscribe button row swaps for
   input + Subscribe/Cancel — same slot, same height, card body untouched,
   so nothing jumps. Cancel swaps the button back. */
const redeemOpen = ref(false);
const codeInput = ref(null);
const code = ref("");
const busy = ref(false);
const err = ref("");

function startSubscribe() {
  code.value = "";
  err.value = "";
  redeemOpen.value = true;
  nextTick(() => codeInput.value?.focus());
}

async function redeem() {
  const c = code.value.trim();
  if (!c || busy.value) return;
  busy.value = true;
  err.value = "";
  try {
    const res = await window.pywebview.api.redeem_code(c);
    if (!res || res.error) {
      err.value = (res && res.error) || "Redemption failed";
      return;
    }
    redeemOpen.value = false;   // success: the plan push flips the badges
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="plan-page">
    <div class="plan-col">
      <h1 class="plan-title">Plan</h1>
      <p class="plan-intro">How the assistant works with your product library.</p>

      <!-- One card per plan; the current one wears the badge and the brand
           border. Equal heights, features aligned row by row. -->
      <div class="plan-grid">
        <div class="plan-card" :class="{ current: !onPro }">
          <div class="pc-head">
            <span class="pc-name">Free</span>
            <span v-if="!onPro" class="pc-cur">Current plan</span>
          </div>
          <div class="pc-price">$0</div>
          <div class="pc-sub">for everyone, forever</div>
          <ul class="pc-feats">
            <li>Personal workspace and assistant</li>
            <li>Colleagues' shared knowledge bases</li>
            <li class="no">Personal knowledge base</li>
          </ul>
          <!-- Current plan keeps a visible but inert Subscribe so both cards
               line up; a downgrade control will take this slot later. -->
          <button v-if="!onPro" class="btn-sm primary pc-cta" disabled>Subscribe</button>
          <div v-else class="pc-cta ph"></div>
        </div>

        <div class="plan-card" :class="{ current: onPro }">
          <div class="pc-head">
            <span class="pc-name">Pro</span>
            <span v-if="onPro" class="pc-cur">Current plan</span>
          </div>
          <div class="pc-price">Beta</div>
          <div class="pc-sub">unlock with a redemption code</div>
          <ul class="pc-feats">
            <li>Everything in Free</li>
            <li>Personal knowledge base — your library, indexed</li>
            <li>Knowledge Graph built from your products</li>
          </ul>
          <!-- The CTA row is the only thing that swaps: Subscribe becomes
               input + Subscribe/Cancel, same row height, card body untouched
               — nothing jumps, nothing to re-read, eyes stay put. -->
          <button v-if="onPro" class="btn-sm primary pc-cta" disabled>Subscribe</button>
          <button v-else-if="!redeemOpen" class="btn-sm primary pc-cta" @click="startSubscribe">
            Subscribe
          </button>
          <div v-else class="rd-inline">
            <input ref="codeInput" v-model="code" type="text" placeholder="Redemption code"
                   spellcheck="false" :disabled="busy"
                   @keydown.enter="redeem" @keydown.esc="redeemOpen = false" />
            <button class="btn-sm primary" :disabled="busy || !code.trim()" @click="redeem">
              {{ busy ? "Redeeming…" : "Subscribe" }}
            </button>
            <button class="btn-sm" :disabled="busy" @click="redeemOpen = false">Cancel</button>
          </div>
          <p v-if="err" class="rd-err">{{ err }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plan-page { height: 100%; overflow-y: auto; display: flex; justify-content: center; padding: 40px 20px; }
.plan-col { width: 100%; max-width: 780px; }
.plan-title {
  font: 700 19px var(--mono); letter-spacing: .5px;
  padding-bottom: 12px; border-bottom: 1px solid var(--border);
}
.plan-intro { font: 400 12px var(--sans); color: var(--text-4); margin: 14px 0 20px; }

/* ── pricing cards ──
   minmax(0,1fr) locks the two columns at equal widths no matter what their
   content wants — otherwise the redemption row's buttons would widen one
   card and squeeze the other, and the swap would feel like a reflow. */
.plan-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; }
.plan-card {
  display: flex; flex-direction: column; gap: 4px;
  background: var(--bg-panel); border: 1px solid var(--border);
  padding: 18px 20px;
}
.plan-card.current { border-color: var(--brand); }
.pc-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.pc-name { font: 600 14px var(--sans); color: var(--text); }
.pc-cur {
  font: 700 8.5px var(--mono); letter-spacing: 1px; text-transform: uppercase;
  color: var(--brand); border: 1px solid var(--brand); padding: 2px 6px;
}
.pc-price { font: 700 24px var(--mono); color: var(--text); margin-top: 10px; }
.pc-sub { font: 400 11px var(--sans); color: var(--text-4); }
.pc-feats {
  list-style: none; margin: 16px 0 18px; padding: 0;
  display: flex; flex-direction: column; gap: 8px;
  font: 400 12px var(--sans); color: var(--text-2);
}
.pc-feats li { padding-left: 16px; position: relative; }
.pc-feats li::before {
  content: ""; position: absolute; left: 0; top: 5px;
  width: 6px; height: 6px; background: var(--brand);
}
/* A missing feature reads as absence, not alarm: dim, hollow square */
.pc-feats li.no { color: var(--text-4); }
.pc-feats li.no::before { background: transparent; border: 1px solid var(--border-soft); }
/* CTA pinned to the card bottom so both cards line up; .ph reserves the
   height on cards without a button (same trick as the KB cards' delete
   column). All three states (Subscribe button, redemption row, .ph) must
   measure exactly 26px, or the swap reflows the card vertically. */
.pc-cta { margin-top: auto; align-self: flex-start; height: 26px; box-sizing: border-box; }
.pc-cta.ph { visibility: hidden; }
/* Current plan's Subscribe is shown but inert — and it must not keep the
   brand fill: a green disabled button reads as "go ahead and click".
   Neutral outline + dim text only, hover included. */
.pc-cta:disabled, .pc-cta:disabled:hover {
  background: transparent; border-color: var(--border-soft);
  color: var(--text-4); cursor: default; filter: none; opacity: 1;
}

/* ── in-place redemption row ──
   Replaces only the Subscribe button: same slot, and every child is pinned
   to the button's exact 26px height, so the card never reflows when the
   interaction opens or closes. */
.rd-inline { margin-top: auto; display: flex; gap: 8px; width: 100%; height: 26px; }
.rd-inline input {
  flex: 1; min-width: 0; height: 26px; box-sizing: border-box;
  background: var(--bg); border: 1px solid var(--border);
  color: var(--text); font: 400 11px var(--mono); letter-spacing: .5px;
  padding: 0 8px; outline: none; text-transform: uppercase;
}
.rd-inline button { height: 26px; box-sizing: border-box; padding-top: 0; padding-bottom: 0;
                    display: inline-flex; align-items: center; }
.rd-inline input:focus { border-color: var(--brand); }
.rd-err { margin: 8px 0 0; font: 400 11px var(--mono); color: var(--red); }
</style>
