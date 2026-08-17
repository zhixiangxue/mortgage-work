<script setup>
/* Settings → Knowledge: which knowledge bases the agent searches.
   Personal = the user's own indexed documents. Shared = other accounts
   mounted read-only, addressed by email only — storage names are derived
   by convention, never surfaced here. Layout follows the LLM tab: an Add
   button in the title row unfolds an inline form, and every entry renders
   as the same quiet card. Whole-config saves: toggles and add/remove
   commit in one shot (store.saveKBConfig). */
import { ref, nextTick, onMounted } from "vue";
import { store, loadKBConfig, saveKBConfig, checkSharedKB } from "../store.js";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const formOpen = ref(false);
const newEmail = ref("");
const formErr = ref("");
const busy = ref(false);
const checking = ref(false);   // existence probe in flight

onMounted(loadKBConfig);

function commit(okMsg) {
  if (busy.value) return;
  busy.value = true;
  saveKBConfig({ personal: store.kb.personal, shared: store.kb.shared }, okMsg)
    .finally(() => { busy.value = false; });
}

/* ── Add form — same unfold idiom as the LLM tab's Add Provider ── */

function openAdd() {
  formOpen.value = true;
  newEmail.value = "";
  formErr.value = "";
  nextTick(() => emailInput.value?.focus());
}
function closeAdd() { formOpen.value = false; formErr.value = ""; }

const emailInput = ref(null);

async function addShared() {
  const email = newEmail.value.trim().toLowerCase();
  if (!email || checking.value || busy.value) return;
  if (!EMAIL_RE.test(email)) { formErr.value = "That doesn't look like an email address"; return; }
  if (store.kb.shared.some(s => s.email === email)) { formErr.value = "Already added"; return; }
  formErr.value = "";

  // The derived dataset/graph must exist (and hold something) before the
  // mount is accepted — a typo'd or never-registered email would otherwise
  // just return silent empty results forever.
  checking.value = true;
  let res;
  try { res = await checkSharedKB(email); }
  finally { checking.value = false; }
  if (!res || res.error) {
    formErr.value = (res && res.error) || "Could not reach the knowledge service";
    return;
  }
  const ragHas = res.rag_exists && res.rag_docs > 0;
  const kgHas = res.kg_exists && res.kg_nodes > 0;
  if (!ragHas && !kgHas) {
    formErr.value = (res.rag_exists || res.kg_exists)
      ? "This account's knowledge base is empty — nothing to share yet."
      : "No knowledge base found.";
    return;
  }

  store.kb.shared.push({ email, enabled: true });
  commit(`Added ${email}`);
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
  const email = store.kb.shared[i].email;
  store.kb.shared.splice(i, 1);
  commit(`Removed ${email}`);
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
        guidelines and products. A colleague's base is read-only — add them
        by email and their indexed documents join your searches.
      </p>

      <!-- Add form unfolds under the title, LLM-tab style -->
      <div v-if="formOpen" class="kb-form">
        <label>Colleague's email</label>
        <input ref="emailInput" v-model="newEmail" type="email"
               placeholder="colleague@company.com" spellcheck="false"
               :disabled="busy || checking" @keydown.enter="addShared" @keydown.esc="closeAdd" />
        <p v-if="formErr" class="kb-err">{{ formErr }}</p>
        <div class="kb-form-row">
          <button class="btn-sm primary" :disabled="busy || checking || !newEmail.trim()" @click="addShared">
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
          <div class="kb-name">Personal knowledge</div>
          <div class="kb-desc">Built from the documents in your workspace.</div>
        </div>
        <label class="toggle" :class="{ on: store.kb.personal }" @click="togglePersonal">
          <span class="slider"></span>
        </label>
        <span class="kb-del ph"></span>
      </div>

      <div v-for="(s, i) in store.kb.shared" :key="s.email"
           class="kb-card" :class="{ off: !s.enabled }">
        <div class="kb-info">
          <div class="kb-name">{{ s.email }}</div>
          <div class="kb-desc">Shared with you · read-only</div>
        </div>
        <label class="toggle" :class="{ on: s.enabled }" @click="toggleShared(i)">
          <span class="slider"></span>
        </label>
        <button class="kb-del" :disabled="busy" title="Remove" @click="removeShared(i)">×</button>
      </div>

      <div v-if="!store.kb.shared.length" class="kb-empty">
        No shared knowledge bases yet. Use Add to mount a colleague's base
        by email.
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
  display: flex; align-items: center; gap: 12px;
  background: var(--bg-panel); border: 1px solid var(--border);
  padding: 14px 18px; margin-bottom: 10px;
}
.kb-info { flex: 1; min-width: 0; }
.kb-name {
  font: 600 13px var(--sans); color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.kb-desc { font: 400 11.5px var(--sans); color: var(--text-4); line-height: 1.55; margin-top: 3px; }
.kb-card.off .kb-name { color: var(--text-3); }
.kb-card.off .kb-desc { color: var(--text-4); opacity: .7; }

/* Delete appears on hover only; the button stays in the DOM (invisible) so
   the toggle column never shifts. .ph is the matching placeholder on the
   personal card. */
.kb-del {
  background: none; border: none; cursor: pointer; flex: none;
  color: var(--text-4); font-size: 15px; line-height: 1; padding: 2px 4px;
  opacity: 0; transition: opacity .12s;
}
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
