<script setup>
/* Memory tab — all memory config happens here.

   States:
   A. Setup (not ready, or ready but not enabled):
      Two stacked sections, each a Provider dropdown + cascaded Model dropdown.
      Only when a section has zero keyed candidates does a small hint link appear.
   B. List (ready + enabled): memory cards with search, edit, delete.
      Toolbar lets you re-pick the extraction model inline.

   "Ready" means BOTH embedding and LLM are configured with valid keys.
   Until ready, the list is unreachable. */
import { ref, computed, watch } from "vue";
import { store,
         loadMemoryConfig, loadMemos,
         openSettings,
         saveMemoryEmbedding, saveMemoryLLM,
         toggleMemory, forgetMemories,
         updateMemo, deleteMemo } from "../store.js";

const ready = ref(false);

/* ---- states ----
   showSetup: anything not fully ready-and-enabled → setup card.
   isList:    ready AND enabled → memory list. */
const isList    = computed(() => store.memory.ready && store.memory.enabled);
const showSetup = computed(() => !isList.value);

/* ---- candidates (only providers with a key) ---- */
const embKeyed = computed(() => (store.memory.candidates || []).filter(c => c.has_key));
const llmKeyed = computed(() => (store.memory.llmCandidates || []).filter(c => c.has_key));
const embHasAny = computed(() => embKeyed.value.length > 0);
const llmHasAny = computed(() => llmKeyed.value.length > 0);

/* ---- cascading dropdowns ---- */
const embProv = ref("");
const embModel = ref("");
const llmProv = ref("");
const llmModel = ref("");
const saving = ref(false);

const embModelOptions = computed(() => {
  const c = embKeyed.value.find(c => c.provider === embProv.value);
  return (c && c.models) || [];
});
const llmModelOptions = computed(() => {
  const c = llmKeyed.value.find(c => c.provider === llmProv.value);
  return (c && c.models) || [];
});

const canEnable = computed(() =>
  !!embProv.value && !!embModel.value &&
  !!llmProv.value && !!llmModel.value);

/* When the config loads and we're in setup mode, pre-fill from saved state */
watch(() => store.memory.ready, (ok) => {
  if (ok) {
    embProv.value = store.memory.embedding?.provider || embProv.value;
    embModel.value = store.memory.embedding?.model || embModel.value;
    llmProv.value = store.memory.llm?.provider || llmProv.value;
    llmModel.value = store.memory.llm?.model || llmModel.value;
  }
}, { immediate: true });

/* When provider changes, auto-select first model of that provider */
watch(embProv, () => {
  const opts = embModelOptions.value;
  if (opts.length && !opts.includes(embModel.value)) embModel.value = opts[0];
});
watch(llmProv, () => {
  const opts = llmModelOptions.value;
  if (opts.length && !opts.includes(llmModel.value)) llmModel.value = opts[0];
});

async function enableMemory() {
  if (!canEnable.value || saving.value) return;
  saving.value = true;
  try {
    await saveMemoryEmbedding(embProv.value, embModel.value);
    await saveMemoryLLM(llmProv.value, llmModel.value);
  } finally { saving.value = false; }
}

/* ---- toolbar re-pick extraction model (list mode) ---- */
const showLlmRePick = ref(false);
const reProv = ref("");
const reModel = ref("");
const reSaving = ref(false);

const reModelOptions = computed(() => {
  const c = llmKeyed.value.find(c => c.provider === reProv.value);
  return (c && c.models) || [];
});

function startLlmRePick() {
  reProv.value = store.memory.llm?.provider || "";
  reModel.value = store.memory.llm?.model || "";
  showLlmRePick.value = true;
}
watch(reProv, () => {
  const opts = reModelOptions.value;
  if (opts.length && !opts.includes(reModel.value)) reModel.value = opts[0];
});
function cancelLlmRePick() { showLlmRePick.value = false; }
async function saveLlmRePick() {
  if (!reProv.value || !reModel.value || reSaving.value) return;
  reSaving.value = true;
  try {
    await saveMemoryLLM(reProv.value, reModel.value);
    showLlmRePick.value = false;
  } finally { reSaving.value = false; }
}

/* ---- toggle / list helpers ---- */
function onToggleMemory() { toggleMemory(!store.memory.enabled); }

let searchTimer = null;
function onSearchInput() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadMemos, 300);
}
const editingId = ref(null);
const editText = ref("");
function startEdit(m) { editingId.value = m.id; editText.value = m.content; }
function cancelEdit() { editingId.value = null; }
async function saveEdit(id) {
  const ok = await updateMemo(id, editText.value);
  if (ok) editingId.value = null;
}
function onEditKey(e, id) {
  if (e.key === "Escape") cancelEdit();
  else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) saveEdit(id);
}
function fmtTime(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

const SVG_EDIT = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`;
const SVG_TRASH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>`;

Promise.all([loadMemoryConfig(), loadMemos()]).finally(() => { ready.value = true; });
</script>

<template>
  <div class="viewer" :class="{ list: isList }">

    <!-- Loading -->
    <div v-if="!ready" class="empty-state">
      <div class="fb-spin"></div>
    </div>

    <!-- ===== A. Setup card ===== -->
    <div v-else-if="showSetup" class="setup-scroll">
      <div class="setup-card">
        <h2>Turn on Work Memory</h2>
        <p class="setup-desc">
          Memory extracts knowledge from your conversations into searchable
          knowledge. Pick an embedding provider and an extraction model below.
        </p>

        <!-- ▏Embedding Provider — cascading dropdowns -->
        <div class="field-group">
          <div class="field-label">Embedding Provider</div>
          <div class="field-row">
            <select v-model="embProv" class="field-select" :disabled="!embHasAny">
              <option value="" disabled>Select provider…</option>
              <option v-for="c in embKeyed" :key="c.provider" :value="c.provider">{{ c.provider }}</option>
            </select>
            <select v-model="embModel" class="field-select" :disabled="!embProv">
              <option value="" disabled>{{ embProv ? 'Select model…' : '—' }}</option>
              <option v-for="m in embModelOptions" :key="m" :value="m">{{ m }}</option>
            </select>
          </div>
          <div v-if="!embHasAny" class="no-key-hint">
            No embedding key configured.
            <a @click="openSettings('embedding')">Open Embedding Settings →</a>
          </div>
        </div>

        <!-- ▏Extraction Model — cascading dropdowns -->
        <div class="field-group">
          <div class="field-label">Extraction Model</div>
          <div class="field-row">
            <select v-model="llmProv" class="field-select" :disabled="!llmHasAny">
              <option value="" disabled>Select provider…</option>
              <option v-for="c in llmKeyed" :key="c.provider" :value="c.provider">{{ c.provider }}</option>
            </select>
            <select v-model="llmModel" class="field-select" :disabled="!llmProv">
              <option value="" disabled>{{ llmProv ? 'Select model…' : '—' }}</option>
              <option v-for="m in llmModelOptions" :key="m" :value="m">{{ m }}</option>
            </select>
          </div>
          <div v-if="!llmHasAny" class="no-key-hint">
            No LLM key configured.
            <a @click="openSettings('models')">Open Model Settings →</a>
          </div>
        </div>

        <!-- One-way door warning -->
        <div v-if="embHasAny && llmHasAny" class="setup-warn">
          Once memories are stored the embedding provider can't be changed.
          To switch, delete all memories first.
        </div>

        <button class="setup-btn" :disabled="!canEnable || saving" @click="enableMemory">
          {{ saving ? "Saving…" : "Enable Memory" }}
        </button>
      </div>
    </div>

    <!-- ===== B. Memory list ===== -->
    <template v-else-if="isList">
      <div class="mem-toolbar">
        <div class="mem-toolbar-info">
          <span class="mem-toolbar-label">
            {{ store.memory.memos.length }} memor{{ store.memory.memos.length === 1 ? 'y' : 'ies' }}
          </span>
          <div class="mem-model-lines">
            <div v-if="store.memory.embedding" class="mm-line">
              <span class="mm-tag">Embed</span>
              {{ store.memory.embedding.provider }} / {{ store.memory.embedding.model }}
            </div>
            <div class="mm-line mm-extract" @click="startLlmRePick">
              <span class="mm-tag">Extract</span>
              {{ store.memory.llm ? (store.memory.llm.provider + ' / ' + store.memory.llm.model) : 'not set' }}
              <span class="mm-change">change</span>
            </div>
          </div>
        </div>
        <div class="toggle" :class="{ on: store.memory.enabled }" @click="onToggleMemory">
          <span class="slider"></span>
        </div>
      </div>

      <!-- Inline re-pick panel -->
      <div v-if="showLlmRePick" class="repick-panel">
        <div class="field-label">Change Extraction Model</div>
        <div class="field-row">
          <select v-model="reProv" class="field-select">
            <option value="" disabled>Select provider…</option>
            <option v-for="c in llmKeyed" :key="c.provider" :value="c.provider">{{ c.provider }}</option>
          </select>
          <select v-model="reModel" class="field-select" :disabled="!reProv">
            <option value="" disabled>{{ reProv ? 'Select model…' : '—' }}</option>
            <option v-for="m in reModelOptions" :key="m" :value="m">{{ m }}</option>
          </select>
        </div>
        <div class="repick-actions">
          <button class="btn-sm primary" :disabled="!reProv || !reModel || reSaving"
                  @click="saveLlmRePick()">{{ reSaving ? "Saving…" : "Save" }}</button>
          <button class="btn-sm" @click="cancelLlmRePick()">Cancel</button>
        </div>
      </div>

      <div class="center-header">
        <div class="search-wrap">
          <input class="search-input" type="text" v-model="store.memory.query"
                 placeholder="Search memories…" @input="onSearchInput" />
        </div>
      </div>

      <div class="item-list">
        <div v-if="store.memory.memos.length" class="cards">
          <div class="cards-header">
            <button class="mem-delete-all" @click="forgetMemories()">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
              Delete All
            </button>
          </div>
          <div v-for="m in store.memory.memos" :key="m.id" class="mem-card">
            <div class="mem-body">
              <div v-if="editingId !== m.id" class="mem-text">
                {{ m.content }}
                <div class="mem-footer">{{ fmtTime(m.created) }}</div>
              </div>
              <textarea v-else class="mem-edit" v-model="editText" rows="3"
                        @keydown="onEditKey($event, m.id)"></textarea>
              <div v-if="editingId === m.id" class="edit-hint">Esc · ⌘Enter</div>
            </div>
            <div v-if="editingId !== m.id" class="mem-actions">
              <button title="Edit" @click="startEdit(m)" v-html="SVG_EDIT"></button>
              <button class="del" title="Delete" @click="deleteMemo(m.id)" v-html="SVG_TRASH"></button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <div class="e-icon">
            <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.5">
              <ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/>
            </svg>
          </div>
          <div class="e-title">Nothing yet</div>
          <div class="e-sub">The agent starts extracting knowledge after your first conversation.</div>
        </div>
      </div>
    </template>

  </div>
</template>

<style scoped>
.viewer { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.viewer.list { background: var(--bg-editor); }

/* ---- Setup ---- */
.setup-scroll { flex: 1; overflow-y: auto; display: flex; justify-content: center; padding: 40px 20px; }
.setup-card {
  width: 100%; max-width: 460px;
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 10px; padding: 24px;
}
.setup-card > h2 { font: 600 15px var(--sans); color: var(--text); margin-bottom: 6px; }
.setup-desc {
  font: 400 12px var(--sans); color: var(--text-4); line-height: 1.6; margin-bottom: 20px;
}

/* Field groups — stacked vertically */
.field-group { margin-bottom: 20px; }
.field-label {
  font: 600 10.5px var(--mono); color: var(--text-3); text-transform: uppercase;
  letter-spacing: .06em; margin-bottom: 6px;
}
.field-row {
  display: flex; gap: 8px; align-items: center;
}
.field-select {
  flex: 1; padding: 7px 10px;
  background: var(--bg-hover); border: 1px solid var(--border);
  color: var(--text-2); font: 400 12px var(--mono);
  border-radius: 6px; outline: none; cursor: pointer;
  min-width: 0;
}
.field-select:focus { border-color: var(--brand); }
.field-select:disabled { opacity: .5; cursor: default; }

.no-key-hint {
  margin-top: 6px; font: 400 10.5px var(--mono); color: var(--text-4);
}
.no-key-hint a { color: var(--brand); cursor: pointer; margin-left: 4px; }
.no-key-hint a:hover { text-decoration: underline; }

.setup-warn {
  margin-bottom: 16px; padding: 10px 12px; background: var(--tint-amber);
  border-radius: 6px; font: 400 11px var(--sans); color: var(--amber); line-height: 1.5;
}
.setup-btn {
  width: 100%; padding: 10px; background: var(--brand); color: var(--on-brand);
  border: none; border-radius: 8px; font: 600 13px var(--sans); cursor: pointer;
}
.setup-btn:disabled { opacity: .4; cursor: default; }
.setup-btn:hover:not(:disabled) { filter: brightness(1.1); }

/* ---- Toolbar ---- */
.mem-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 20px; border-bottom: 1px solid var(--border); background: var(--bg-panel);
}
.mem-toolbar-info { flex: 1; min-width: 0; }
.mem-toolbar-label { font: 400 11px var(--mono); color: var(--text-4); }
.mem-model-lines { margin-top: 4px; display: flex; flex-direction: column; gap: 2px; }
.mm-line { font: 400 10px var(--mono); color: var(--text-4); display: flex; align-items: center; gap: 5px; }
.mm-tag {
  font: 500 8px var(--mono); padding: 1px 4px; border-radius: 2px;
  background: var(--bg-hover); color: var(--text-3); text-transform: uppercase; letter-spacing: .05em;
}
.mm-extract { cursor: pointer; transition: color .15s; }
.mm-extract:hover { color: var(--text-2); }
.mm-change { margin-left: 6px; color: var(--brand); }

.repick-panel {
  padding: 14px 20px; border-bottom: 1px solid var(--border); background: var(--bg-panel);
}
.repick-actions { display: flex; gap: 8px; margin-top: 8px; }

.toggle { position: relative; width: 30px; height: 17px; flex-shrink: 0; cursor: pointer; }
.toggle .slider { position: absolute; cursor: pointer; inset: 0; background: var(--border-soft); border-radius: 3px; transition: .25s; }
.toggle .slider::before { content: ""; position: absolute; height: 11px; width: 11px; left: 3px; top: 3px; background: var(--text); border-radius: 2px; transition: .25s; }
.toggle.on .slider { background: var(--brand); }
.toggle.on .slider::before { transform: translateX(13px); background: var(--on-brand); }

/* ---- Search ---- */
.center-header { padding: 14px 20px; border-bottom: 1px solid var(--border); display: flex; align-items: center; }
.search-wrap { flex: 1; }
.search-input {
  background: var(--bg-hover); border: 1px solid var(--border); color: var(--text-2);
  font: 400 12px var(--sans); padding: 6px 10px; border-radius: 6px; outline: none; width: 100%;
}
.search-input:focus { border-color: var(--text-4); }
.search-input::placeholder { color: var(--text-4); }

/* ---- Cards ---- */
.item-list { flex: 1; overflow-y: auto; padding: 8px 20px; }
.cards { display: flex; flex-direction: column; gap: 6px; }
.cards-header { display: flex; justify-content: flex-end; padding-bottom: 6px; }
.mem-card {
  padding: 12px 14px; background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 8px; display: flex; align-items: flex-start; gap: 12px; transition: border-color .15s;
}
.mem-card:hover { border-color: var(--border-soft); }
.mem-body { flex: 1; min-width: 0; }
.mem-text { font: 400 12.5px var(--sans); color: var(--text-2); line-height: 1.55; white-space: pre-wrap; word-break: break-word; }
.mem-footer { font: 400 9.5px var(--mono); color: var(--text-4); margin-top: 6px; }
.mem-edit {
  width: 100%; background: var(--bg-hover); border: 1px solid var(--border); color: var(--text);
  font: 400 12.5px var(--sans); line-height: 1.55; padding: 8px 10px; border-radius: 6px; resize: vertical; outline: none;
}
.mem-edit:focus { border-color: var(--brand); }
.edit-hint { font: 400 9px var(--mono); color: var(--text-4); margin-top: 4px; }
.mem-actions { display: flex; gap: 2px; opacity: 0; transition: opacity .15s; flex-shrink: 0; }
.mem-card:hover .mem-actions { opacity: 1; }
.mem-actions button {
  width: 24px; height: 24px; display: flex; align-items: center; justify-content: center;
  border: none; background: none; border-radius: 4px; cursor: pointer; color: var(--text-4);
}
.mem-actions button:hover { background: var(--bg-raise); color: var(--text-2); }
.mem-actions button.del:hover { background: rgba(235,54,28,.12); color: var(--red); }
.mem-actions button :deep(svg) { width: 13px; height: 13px; }
.mem-delete-all {
  display: flex; align-items: center; gap: 5px; padding: 4px 10px;
  background: none; border: 1px solid var(--border); border-radius: 4px;
  font: 400 10.5px var(--mono); color: var(--text-4); cursor: pointer;
}
.mem-delete-all:hover { color: var(--red); border-color: var(--red); background: rgba(235,54,28,.08); }

/* ---- Empty ---- */
.empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px; text-align: center; }
.fb-spin { width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--border); border-top-color: var(--brand); animation: fb-rot 0.7s linear infinite; }
@keyframes fb-rot { to { transform: rotate(360deg); } }
.e-icon { color: var(--text-4); margin-bottom: 16px; }
.e-title { font: 600 15px var(--sans); color: var(--text-2); margin-bottom: 6px; }
.e-sub { font: 400 12px var(--sans); color: var(--text-4); max-width: 360px; line-height: 1.6; }

/* Shared btn */
.btn-sm {
  padding: 5px 12px; border: 1px solid var(--border); background: var(--bg-panel);
  font: 400 11px var(--mono); color: var(--text-2); cursor: pointer; border-radius: 4px;
}
.btn-sm:hover { border-color: var(--text-4); }
.btn-sm.primary { background: var(--brand); color: var(--on-brand); border-color: var(--brand); }
.btn-sm.primary:disabled { opacity: .4; cursor: default; }
</style>
