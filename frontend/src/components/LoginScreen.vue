<script setup>
import { ref, computed } from "vue";
import { store, showToast } from "../store.js";
import { bootAfterLogin } from "../main.js";

/* Single-screen login: the code section expands in place below the email —
   no second page, no step indicator. Trigger matrix once all 6 digits land:
   - returning user → auto-submit, zero extra clicks (nothing irreversible);
   - new user → NEVER auto-submit. Region + code light up an explicit
     SET UP WORKSPACE button, because the region pick is freely reversible
     right up to that click — and provisioning after it is not.
   Approved interaction mock: tmp/login-redesign.html */

const email = ref("");
const sent = ref(false);
const isNew = ref(false);       // server said this email has no account yet
const region = ref("");         // '' until a first-time user picks
const digits = ref(Array(6).fill(""));
const busy = ref(false);
const status = ref("");
const statusErr = ref(false);
const codeErr = ref(false);     // shake + red borders on a wrong code
const nudge = ref(false);       // code complete but no region picked yet

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const code = computed(() => digits.value.join(""));
const confirmReady = computed(() => isNew.value && region.value && code.value.length === 6 && !busy.value);

/* First digit box — queried live instead of cached (see digit mechanics). */
const firstBox = () => document.querySelector("#login-box .ldigit");

async function sendCode() {
  setStatus("");
  const addr = email.value.trim().toLowerCase();
  if (!EMAIL_RE.test(addr)) { setStatus("Enter an email first.", true); return; }
  busy.value = true;
  try {
    const res = await window.pywebview.api.login_request_code(addr);
    if (res && res.error) { setStatus(res.error, true); return; }
    email.value = addr;             // lock the address; reset() unlocks it
    isNew.value = !!res.isNew;
    sent.value = true;
    // The expanded section animates in — focus once it's rendered.
    setTimeout(() => firstBox() && firstBox().focus(), 200);
  } catch (e) {
    setStatus(`Login failed: ${(e && e.message) || e}`, true);
  } finally {
    busy.value = false;
  }
}

function pick(r) {
  if (busy.value) return;
  region.value = r;
  nudge.value = false;
  setStatus("");
}

/* ── Digit-box mechanics: advance, backspace, paste.
      Focus moves through DOM siblings, never a ref array — Vue recreates
      function refs on every re-render (old one gets null first), so a cached
      element list silently goes stale mid-typing. ── */
function onDigitInput(i, e) {
  const el = e.target;
  const v = el.value.replace(/\D/g, "").slice(-1);
  digits.value[i] = v;
  el.value = v;   // keep the DOM honest when Vue skips a same-value patch
  codeErr.value = false;
  if (v && i < 5) el.parentElement.children[i + 1].focus();
  maybeFinish();
}
function onDigitKeydown(i, e) {
  if (e.key === "Backspace" && !digits.value[i] && i > 0)
    e.target.parentElement.children[i - 1].focus();
}
function onDigitPaste(e) {
  const t = (e.clipboardData.getData("text") || "").replace(/\D/g, "").slice(0, 6);
  if (!t) return;
  e.preventDefault();
  t.split("").forEach((ch, j) => (digits.value[j] = ch));
  e.target.parentElement.children[Math.min(t.length, 5)].focus();
  maybeFinish();
}

function maybeFinish() {
  if (busy.value || code.value.length < 6) return;
  if (!isNew.value) { verify(""); return; }        // returning user: zero clicks
  // New user: no auto-fire — wait for region + the explicit confirm click.
  if (!region.value) {
    nudge.value = true;
    setStatus("Now pick your region below.", false);
    // The region block sits right below the digits — hand the focus down so
    // the flow keeps moving instead of stalling on the keyboard.
    setTimeout(() => document.querySelector("#login-box .lopt")?.focus(), 60);
  }
}

async function verify(pickedRegion) {
  busy.value = true;
  setStatus(pickedRegion ? "Creating your workspace…" : "Checking code…");
  try {
    const res = await window.pywebview.api.login_verify(email.value, code.value, pickedRegion);
    if (res && res.error) { wrongCode(res.error); return; }
    showToast(`Welcome, ${res.user.name}`);
    bootAfterLogin();
  } catch (e) {
    setStatus(`Login failed: ${(e && e.message) || e}`, true);
    busy.value = false;
  }
}

function finish() {
  if (!confirmReady.value) return;
  verify(region.value);
}

function wrongCode(msg) {
  codeErr.value = true;
  digits.value = Array(6).fill("");
  firstBox() && firstBox().focus();
  // Provisioning errors ("couldn't set up your workspace: …") land here too —
  // keep them visible verbatim; plain wrong codes get the short form.
  setStatus(msg && msg.includes("workspace") ? msg : "Wrong code — try again.", true);
  busy.value = false;
}

function setStatus(msg, isErr) {
  status.value = msg;
  statusErr.value = !!isErr;
}

function reset() {
  sent.value = false;
  isNew.value = false;
  region.value = "";
  digits.value = Array(6).fill("");
  nudge.value = false;
  codeErr.value = false;
  setStatus("");
}
</script>

<template>
  <div id="login">
    <div id="login-box">
      <div id="login-logo"><span class="mark">M</span><span class="word">MORTGAGE <b>WORK</b></span></div>

      <div class="ltitle">Sign in</div>

      <!-- SEND button lives inside the input; email locks once the code is out -->
      <div class="lin-wrap">
        <input class="lin" type="email" v-model="email" placeholder="you@company.com"
               :disabled="sent || busy" @keydown.enter="sendCode" autofocus />
        <button class="lin-btn" :disabled="sent || busy" @click="sendCode">
          <span v-if="busy && !sent" class="lspin"></span>{{ sent ? "SENT ✓" : (busy ? "SENDING" : "SEND CODE") }}
        </button>
      </div>

      <!-- Everything below expands IN PLACE after the code is sent -->
      <div class="lafter" :class="{ open: sent }">
        <div class="lsent">
          Sent to <b>{{ email }}</b> · <a class="llink" @click="sendCode">send again</a>
        </div>

        <!-- Six boxes first: sending a code implies typing it next — the
             instinctive follow-up, nothing inserted in between. Square, and
             flush with the email input above:
             min-width: 0 is load-bearing (<input> in a flex row otherwise
             refuses to shrink below its intrinsic size); aspect-ratio keeps
             each box square while flex: 1 keeps the row width identical. -->
        <div class="lcode-row" :class="{ err: codeErr, checking: busy && sent }">
          <input v-for="i in 6" :key="i" class="ldigit" maxlength="1" inputmode="numeric"
                 :value="digits[i - 1]" :disabled="busy"
                 @input="onDigitInput(i - 1, $event)"
                 @keydown="onDigitKeydown(i - 1, $event)"
                 @paste="onDigitPaste" />
        </div>

        <!-- New users only: the one irreversible choice, kept to one line.
             Below the code so the verify instinct isn't interrupted; it
             lights up as the step after the digits are done. -->
        <div v-if="isNew" class="lregion" :class="{ nudge }">
          <div class="lhint">Where will you mostly work?
            <span class="lwarn">Can't be changed later.</span></div>
          <div class="lregion-row">
            <button class="lopt" :class="{ on: region === 'intl' }" :disabled="busy"
                    @click="pick('intl')">International</button>
            <button class="lopt" :class="{ on: region === 'cn' }" :disabled="busy"
                    @click="pick('cn')">中国大陆 · Mainland China</button>
          </div>
        </div>

        <!-- New users only: explicit final click (see trigger matrix above) -->
        <button v-if="isNew" class="lbtn" :disabled="!confirmReady" @click="finish">
          {{ busy && region ? "SETTING UP…" : "SET UP WORKSPACE" }}
        </button>

        <div class="lstatus" :class="{ err: statusErr }">{{ status }}</div>
        <a class="llink back" @click="reset">← use a different email</a>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Full-screen replacement for the workspace shell — same terminal aesthetic
   as the boot overlay so login reads as part of startup, not an afterthought. */
#login {
  position: fixed; inset: 0; z-index: 998; background: var(--bg);
  display: flex; align-items: center; justify-content: center;
}
#login-box { width: 380px; font: 400 12px var(--mono); display: flex; flex-direction: column; }
#login-logo { display: flex; align-items: center; gap: 9px; margin-bottom: 26px; }
#login-logo .mark {
  width: 22px; height: 22px; background: var(--brand); color: var(--on-brand);
  font: 700 13px var(--mono); display: flex; align-items: center; justify-content: center;
}
#login-logo .word { font: 700 12px var(--mono); letter-spacing: 2px; color: var(--text); }
#login-logo .word b { color: var(--brand); }
.ltitle { font: 700 13px var(--mono); letter-spacing: 2px; color: var(--text); text-transform: uppercase; margin-bottom: 14px; }

/* Email input with the SEND button inside it */
.lin-wrap { position: relative; margin-bottom: 12px; }
.lin {
  width: 100%; box-sizing: border-box; padding: 10px 96px 10px 12px;
  background: var(--bg-panel, transparent); color: var(--text);
  border: 1px solid var(--border); border-radius: 3px;
  font: 400 12px var(--mono); outline: none;
}
.lin:focus { border-color: var(--brand); }
.lin:disabled { color: var(--text-3); }
.lin-btn {
  position: absolute; right: 5px; top: 50%; transform: translateY(-50%);
  padding: 6px 12px; cursor: pointer; border: none; border-radius: 2px;
  background: var(--brand); color: var(--on-brand);
  font: 700 10px var(--mono); letter-spacing: 1.5px;
  display: inline-flex; align-items: center; gap: 5px;
}
.lin-btn:not(:disabled):hover { filter: brightness(1.15); }
.lin-btn:disabled { opacity: .55; cursor: default; }
/* In-button spinner while the code mail is on its way */
.lspin {
  width: 9px; height: 9px; border-radius: 50%; flex: none;
  border: 2px solid rgba(0, 0, 0, .25); border-top-color: var(--on-brand);
  animation: lrot .6s linear infinite;
}
@keyframes lrot { to { transform: rotate(360deg); } }

/* Expanding section — same screen, no navigation */
.lafter {
  overflow: hidden; max-height: 0; opacity: 0;
  transition: max-height .35s ease, opacity .3s ease;
  border-top: 1px dashed var(--border); margin-top: 4px;
}
.lafter.open { max-height: 420px; opacity: 1; padding-top: 16px; }
.lsent { color: var(--text-3); font-size: 11px; margin-bottom: 12px; }
.lsent b { color: var(--text-2); }

/* Region block (new users only) */
.lregion { margin-bottom: 14px; }
.lhint { color: var(--text-3); font-size: 11px; line-height: 1.6; margin-bottom: 8px; }
/* The one irreversible statement on this screen — red so it can't be skimmed past */
.lwarn { color: var(--red); font-weight: 700; }
.lregion-row { display: flex; gap: 8px; }
.lopt {
  flex: 1; padding: 10px 8px; cursor: pointer;
  background: transparent; color: var(--text-2);
  border: 1px solid var(--border); border-radius: 3px;
  font: 400 11px var(--mono);
}
.lopt:not(:disabled):hover { border-color: var(--brand); color: var(--text); }
.lopt.on { border-color: var(--brand); color: var(--brand); background: color-mix(in srgb, var(--brand) 10%, transparent); }
.lregion.nudge .lopt { border-color: var(--amber); }

/* Six code boxes — square, and flush with the region row:
   min-width: 0 is load-bearing (<input> in a flex row otherwise refuses to
   shrink below its intrinsic size); aspect-ratio keeps each box square
   while flex: 1 keeps the row width identical to the region row above. */
.lcode-row { display: flex; gap: 8px; margin-bottom: 14px; }
.ldigit {
  flex: 1; min-width: 0; aspect-ratio: 1; text-align: center;
  background: var(--bg-panel, transparent); color: var(--text);
  border: 1px solid var(--border); border-radius: 3px;
  font: 700 15px var(--mono); outline: none; caret-color: var(--brand);
}
.ldigit:focus { border-color: var(--brand); }
.ldigit.err, .lcode-row.err .ldigit { border-color: var(--red); }
/* While a verify/setup request is in flight, breathe — the UI is alive,
   not frozen. Border-only so layout never shifts mid-wait. */
.lcode-row.checking .ldigit { animation: lpulse 1.2s ease-in-out infinite; }
@keyframes lpulse { 50% { border-color: var(--brand); } }
@keyframes lshake { 25% { transform: translateX(-3px); } 75% { transform: translateX(3px); } }
.lcode-row.err { animation: lshake .25s ease 2; }

.lbtn {
  padding: 10px 22px; cursor: pointer;
  background: var(--brand); color: var(--on-brand); border: none; border-radius: 3px;
  font: 700 11px var(--mono); letter-spacing: 2px;
}
.lbtn:disabled { opacity: .45; cursor: default; }
.lbtn:not(:disabled):hover { filter: brightness(1.15); }
.lstatus { margin-top: 12px; color: var(--text-3); font-size: 11px; line-height: 1.5; min-height: 14px; }
.lstatus.err { color: var(--red); }
.llink { color: var(--brand); cursor: pointer; text-decoration: none; }
.llink:hover { text-decoration: underline; }
.llink.back { display: inline-block; margin-top: 10px; color: var(--text-3); }
</style>
