<script setup>
/* Settings → Knowledge: which knowledge bases the agent searches.
   Personal = the user's own indexed documents. Shared = other accounts
   mounted read-only, addressed by knowledge-base ID — an ID the owner
   copied and handed over, never an email someone guessed. Layout follows
   the LLM tab: an Add button in the title row unfolds an inline form, and
   every entry renders as the same quiet card. Whole-config saves: toggles
   and add/remove commit in one shot (store.saveKBConfig). */
import { ref, computed, nextTick, onMounted } from "vue";
import { store, loadKBConfig, saveKBConfig, checkSharedKB } from "../store.js";

// A knowledge-base ID is an xxh64 hexdigest — exactly 16 hex characters.
const ID_RE = /^[0-9a-f]{16}$/i;

// Same trash shape as chat / memory delete buttons
const SVG_TRASH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>`;

// Card title marks: one person = your own base, two people = a colleague's
const SVG_USER = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
const SVG_USERS = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`;

const formOpen = ref(false);
const newId = ref("");
const formErr = ref("");
const busy = ref(false);
const checking = ref(false);   // existence probe in flight

// The logged-in user's own KB ID — surfaced on the personal card so it can
// be copied and handed to a colleague.
const myId = computed(() => (store.user && store.user.id) || "");

// Copy feedback stays in place: the button flips to a check mark and back
// after 2s — no toast, the confirmation happens where the action happened.
const copied = ref(false);
let copyTimer = null;

onMounted(loadKBConfig);

function commit(okMsg) {
  if (busy.value) return;
  busy.value = true;
  saveKBConfig({ personal: store.kb.personal, shared: store.kb.shared }, okMsg)
    .finally(() => { busy.value = false; });
}

function legacyCopy(text) {
  // WKWebView occasionally denies navigator.clipboard — the classic
  // textarea + execCommand path still works there.
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { /* stay silent */ }
  ta.remove();
  return ok;
}

async function copyId() {
  if (!myId.value || copied.value) return;
  let ok = true;
  try { await navigator.clipboard.writeText(myId.value); }
  catch { ok = legacyCopy(myId.value); }
  if (!ok) return;
  copied.value = true;
  clearTimeout(copyTimer);
  copyTimer = setTimeout(() => { copied.value = false; }, 2000);
}

/* ── Add form — same unfold idiom as the LLM tab's Add Provider ── */

function openAdd() {
  formOpen.value = true;
  newId.value = "";
  formErr.value = "";
  nextTick(() => idInput.value?.focus());
}
function closeAdd() { formOpen.value = false; formErr.value = ""; }

const idInput = ref(null);

async function addShared() {
  const kbId = newId.value.trim().toLowerCase();
  if (!kbId || checking.value || busy.value) return;
  if (!ID_RE.test(kbId)) { formErr.value = "A knowledge base ID is 16 hex characters"; return; }
  if (kbId === myId.value) { formErr.value = "That's your own knowledge base"; return; }
  if (store.kb.shared.some(s => s.id === kbId)) { formErr.value = "Already added"; return; }
  formErr.value = "";

  // The dataset/graph behind the ID must exist (and hold something) before
  // the mount is accepted — a bogus ID would otherwise just return silent
  // empty results forever.
  checking.value = true;
  let res;
  try { res = await checkSharedKB(kbId); }
  finally { checking.value = false; }
  if (!res || res.error) {
    formErr.value = (res && res.error) || "Could not reach the knowledge service";
    return;
  }
  const ragHas = res.rag_exists && res.rag_docs > 0;
  const kgHas = res.kg_exists && res.kg_nodes > 0;
  if (!ragHas && !kgHas) {
    formErr.value = (res.rag_exists || res.kg_exists)
      ? "This knowledge base is empty — nothing to share yet."
      : "No knowledge base found for that ID.";
    return;
  }

  store.kb.shared.push({ id: kbId, enabled: true });
  commit("Knowledge base added");
  closeAdd();
}

/* ── Card actions ── */

function togglePersonal() {
  store.kb.personal = !store.kb.personal;
  commit(store.kb.personal ? "Personal knowledge on" : "Personal knowledge off");
}

function toggleShared(i) {
  store.kb.shared[i].enabled = !store.kb.shared[i].enabled;
  commit("");
}

// No confirmation: removing a mount only stops querying it — the colleague's
// knowledge base itself is untouched, and re-adding is one click.
function removeShared(i) {
  store.kb.shared.splice(i, 1);
  commit("Knowledge base removed");
}
</script>

<template>
  <div class="kb-page">
    <div class="kb-col">
      <h1 class="kb-title">
        Knowledge
        <button class="btn-sm primary kb-add" @click="openAdd()">Add</button>
      </h1>
      <p class="kb-intro">
        Which knowledge bases the agent searches when you ask about
        guidelines and products. A colleague's base is read-only — ask them
        for their knowledge base ID (shown on their own Knowledge page) and
        add it here.
      </p>

      <!-- Add form unfolds under the title, LLM-tab style -->
      <div v-if="formOpen" class="kb-form">
        <label>Colleague's knowledge base ID</label>
        <input ref="idInput" v-model="newId" type="text"
               placeholder="e.g. 3f9a2b1c4d5e6f70" spellcheck="false"
               :disabled="busy || checking" @keydown.enter="addShared" @keydown.esc="closeAdd" />
        <p v-if="formErr" class="kb-err">{{ formErr }}</p>
        <div class="kb-form-row">
          <button class="btn-sm primary" :disabled="busy || checking || !newId.trim()" @click="addShared">
            {{ checking ? "Checking…" : "Add" }}
          </button>
          <button class="btn-sm" :disabled="busy || checking" @click="closeAdd">Cancel</button>
        </div>
      </div>

      <!-- One card shape for every knowledge base: name + description left,
           controls right. Every card reserves the delete column, so the
           toggles line up whether or not a × is ever shown there. -->
      <div class="kb-card" :class="{ off: !store.kb.personal }">
        <div class="kb-info">
          <div class="kb-name">
            <span class="kb-ico" v-html="SVG_USER"></span>
            <span class="kb-txt">Personal knowledge</span>
          </div>
          <div class="kb-desc">Built from the documents in your workspace.</div>
        </div>
        <label class="toggle" :class="{ on: store.kb.personal }" @click="togglePersonal">
          <span class="slider"></span>
        </label>
        <span class="kb-del ph"></span>
        <!-- The owner copies this ID and hands it to a colleague — the only
             way to mount this KB. Full-width footer strip under a hairline,
             so it reads as card metadata rather than description text. -->
        <div v-if="myId" class="kb-id-row">
          <span class="kb-id-label">Your knowledge base ID</span>
          <code class="kb-id-value">{{ myId }}</code>
          <button class="kb-copy" :class="{ done: copied }" title="Copy ID" @click="copyId">
            <svg v-if="copied" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
            <template v-else>Copy</template>
          </button>
        </div>
      </div>

      <div v-for="(s, i) in store.kb.shared" :key="s.id"
           class="kb-card" :class="{ off: !s.enabled }">
        <div class="kb-info">
          <div class="kb-name">
            <span class="kb-ico" v-html="SVG_USERS"></span>
            <span class="kb-txt">{{ s.id }}</span>
          </div>
          <div class="kb-desc">Shared with you · read-only</div>
        </div>
        <label class="toggle" :class="{ on: s.enabled }" @click="toggleShared(i)">
          <span class="slider"></span>
        </label>
        <button class="kb-del" :disabled="busy" title="Remove" @click="removeShared(i)" v-html="SVG_TRASH"></button>
      </div>

      <div v-if="!store.kb.shared.length" class="kb-empty">
        No shared knowledge bases yet. Use Add to mount a colleague's base
        with their knowledge base ID.
      </div>
    </div>
  </div>
</template>

<style scoped>
.kb-page { height: 100%; overflow-y: auto; display: flex; justify-content: center; padding: 40px 20px; }
.kb-col { width: 100%; max-width: 560px; }
.kb-title {
  font: 700 19px var(--mono); letter-spacing: .5px;
  padding-bottom: 12px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 12px;
}
.kb-add { margin-left: auto; }
.kb-intro { font: 400 12px var(--sans); color: var(--text-4); line-height: 1.6; margin: 14px 0 18px; }

/* Add form — same tonal vocabulary as the LLM tab's .add-form */
.kb-form {
  border: 1px solid var(--border); background: var(--bg-hover);
  padding: 14px; margin-bottom: 18px;
}
.kb-form label {
  display: block; font: 700 9px var(--mono); letter-spacing: 1.5px;
  text-transform: uppercase; color: var(--text-4); margin-bottom: 5px;
}
.kb-form input {
  width: 100%; background: var(--bg); border: 1px solid var(--border);
  color: var(--text); font: 400 11px var(--mono); padding: 7px 9px; outline: none;
}
.kb-form input:focus { border-color: var(--brand); }
.kb-err { margin: 8px 0 0; font: 400 11px var(--mono); color: var(--red); }
.kb-form-row { display: flex; gap: 8px; margin-top: 10px; }

/* One card shape for personal and shared alike */
.kb-card {
  display: flex; flex-wrap: wrap; align-items: center; gap: 12px;
  background: var(--bg-panel); border: 1px solid var(--border);
  padding: 14px 18px; margin-bottom: 10px;
}
.kb-info { flex: 1; min-width: 0; }
.kb-name {
  display: flex; align-items: center; gap: 7px; min-width: 0;
  font: 600 13px var(--sans); color: var(--text);
}
/* Title mark: one person = own base, two people = a colleague's */
.kb-ico { flex: none; display: inline-flex; color: var(--text-4); }
/* :deep() — the svg arrives via v-html, so it never gets the scope id */
.kb-ico :deep(svg) { width: 13px; height: 13px; }
.kb-txt { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-desc { font: 400 11.5px var(--sans); color: var(--text-4); line-height: 1.55; margin-top: 3px; }

/* The owner's own KB ID — a full-width footer strip under a hairline.
   width:calc(100% + 2×18px) + negative side margins stretch it across the
   card's own padding so the divider runs edge to edge (flex-basis alone
   would only shift the box left, leaving the right edge 18px short).
   Top spacing comes from the card's row gap, so margin-top stays 0. */
.kb-id-row {
  width: calc(100% + 36px);
  margin: 0 -18px -14px;
  padding: 9px 18px;
  border-top: 1px solid var(--border);
  display: flex; align-items: center; gap: 10px;
}
.kb-id-label {
  font: 700 9px var(--mono); letter-spacing: 1.5px;
  text-transform: uppercase; color: var(--text-4);
}
.kb-id-value { flex: 1; font: 400 11px var(--mono); color: var(--text-3); letter-spacing: .4px; }
/* Fixed footprint so the "Copy" → check flip never shifts the layout */
.kb-copy {
  background: none; border: 1px solid var(--border); color: var(--text-4);
  font: 700 8.5px var(--mono); letter-spacing: 1px; text-transform: uppercase;
  min-width: 52px; height: 20px; padding: 0;
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer;
}
.kb-copy svg { width: 11px; height: 11px; }
.kb-copy:hover, .kb-copy.done { color: var(--brand); border-color: var(--brand); }
.kb-card.off .kb-name { color: var(--text-3); }
.kb-card.off .kb-ico { opacity: .7; }
.kb-card.off .kb-desc { color: var(--text-4); opacity: .7; }

/* Delete appears on hover only; the button stays in the DOM (invisible) so
   the toggle column never shifts. .ph is the matching placeholder on the
   personal card. Fixed width: the placeholder span has no glyph content, so
   without it the button (× + padding) would be wider and the toggles on the
   two card kinds would sit at different x positions. */
.kb-del {
  background: none; border: none; cursor: pointer; flex: none;
  color: var(--text-4); line-height: 1;
  width: 24px; height: 20px; padding: 0;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity .12s;
}
/* :deep() — the svg arrives via v-html, so it never gets the scope id */
.kb-del :deep(svg) { width: 13px; height: 13px; }
.kb-card:hover .kb-del:not(.ph) { opacity: 1; }
.kb-del:hover { color: var(--red); }
.kb-del.ph { visibility: hidden; pointer-events: none; }

.kb-empty {
  border: 1px dashed var(--border-soft); padding: 16px;
  font: 400 11.5px/1.7 var(--mono); color: var(--text-4);
}

/* Same switch as the Memory tab */
.toggle { position: relative; width: 30px; height: 17px; flex-shrink: 0; cursor: pointer; }
.toggle .slider { position: absolute; cursor: pointer; inset: 0; background: var(--border-soft); border-radius: 3px; transition: .25s; }
.toggle .slider::before { content: ""; position: absolute; height: 11px; width: 11px; left: 3px; top: 3px; background: var(--text); border-radius: 2px; transition: .25s; }
.toggle.on .slider { background: var(--brand); }
.toggle.on .slider::before { transform: translateX(13px); background: var(--on-brand); }
</style>
