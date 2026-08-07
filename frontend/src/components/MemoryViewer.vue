<script setup>
/* Editor pane for the Memory tab. Three visual states:
   A. Memory not enabled — quiet "it's off" empty state.
   B. Enabled but no embedder configured — setup card, pick a provider or
      guided to Settings → Embedding to add a key.
   C. Enabled and configured — scrollable memory list with inline search,
      edit and delete.

   The provider choice is a one-way door while memories exist (embedding
   model swap = incompatible vector space), so the setup card only renders
   when the store is empty. */
import { ref, computed } from "vue";
import { store, showToast,
         loadMemoryConfig, loadMemos,
         openSettings,
         saveMemoryEmbedding,
         toggleMemory, forgetMemories,
         updateMemo, deleteMemo } from "../store.js";

/* ---- state ---------------------------------------------------------------- */
const selected = ref("");        // which provider row is picked
const selectedModel = ref("");   // which model of that provider
const saving = ref(false);
const ready = ref(false);        // true after the first config + memos load

/* Three mutually exclusive states, derived from the store */
const isOff    = computed(() => !store.memory.enabled);
const isSetup  = computed(() => store.memory.enabled && !store.memory.embedding);
const isList   = computed(() => store.memory.enabled && !!store.memory.embedding);

/* Derived: candidates ready to display in the picker grid */
const candidates = computed(() => store.memory.candidates || []);

/* Models for the currently selected provider */
const selModels = computed(() => {
  const c = candidates.value.find(c => c.provider === selected.value);
  return (c && c.available_models) || [];
});

/* ---- setup card ----------------------------------------------------------- */
function pickProvider(p) {
  // Only selectable if a key is already configured in Settings → Embedding
  if (!p.has_key) return;
  selected.value = p.provider;
  selectedModel.value = p.model;  // default to first model
}

async function enableMemory() {
  if (!selected.value || !selectedModel.value || saving.value) return;
  const p = candidates.value.find(c => c.provider === selected.value);
  if (!p || !p.has_key) return;
  saving.value = true;
  try {
    await saveMemoryEmbedding(selected.value, selectedModel.value);
  } finally { saving.value = false; }
}

function goToEmbeddingSettings() {
  openSettings("embedding");
}

/* ---- memory list ---------------------------------------------------------- */
/* Search is debounced 300 ms — the same feel as the demo. */
let searchTimer = null;
function onSearchInput() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadMemos, 300);
}

/* Inline editing */
const editingId = ref(null);
const editText = ref("");
function startEdit(memo) {
  editingId.value = memo.id;
  editText.value = memo.content;
}
function cancelEdit() { editingId.value = null; }
async function saveEdit(id) {
  const ok = await updateMemo(id, editText.value);
  if (ok) editingId.value = null;
}

/* Keydown: Esc to cancel, Cmd+Enter / Ctrl+Enter to save */
function onEditKey(e, id) {
  if (e.key === "Escape") cancelEdit();
  else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) saveEdit(id);
}

/* Timestamp formatting: created is unix seconds from Python */
function fmtTime(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/* SVG icons — same paths as the demo so the LO recognises them from there */
const SVG_EDIT = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`;
const SVG_TRASH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>`;

/* ---- memory toggle (enable / disable, now self-contained) ---------------- */
function onToggleMemory() {
  if (!store.memory.embedding) {
    // No embedder yet: just flip the flag locally so the setup card appears
    store.memory.enabled = !store.memory.enabled;
    return;
  }
  toggleMemory(!store.memory.enabled);
}

/* Ensure the config is fresh on mount.  Show nothing until both calls settle
   so the LO never sees a brief "Nothing yet" before data arrives. */
Promise.all([loadMemoryConfig(), loadMemos()]).finally(() => { ready.value = true; });
</script>

<template>
  <div class="viewer" :class="{ list: isList }">

    <!-- Loading: config hasn't arrived yet — don't flash "off" or "nothing" -->
    <div v-if="!ready" class="empty-state">
      <div class="fb-spin"></div>
      <div class="e-title" style="margin-top:16px">Loading…</div>
    </div>

    <!-- ===== A. Memory off ===== -->
    <div v-else-if="isOff" class="empty-state">
      <div class="e-icon">
        <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.5">
          <ellipse cx="12" cy="5" rx="9" ry="3"/>
          <path d="M3 5v14a9 3 0 0 0 18 0V5"/>
        </svg>
      </div>
      <div class="e-title">Memory is off</div>
      <div class="e-sub">
        Enable it to start. Once on, the agent will extract knowledge from
        your conversations automatically.
      </div>
      <button class="enable-btn" @click="onToggleMemory">Enable Memory</button>
    </div>

    <!-- ===== B. Setup card (enabled, no embedder) ===== -->
    <div v-else-if="isSetup" class="setup-card">
      <h2>Turn on Work Memory</h2>
      <p class="setup-desc">
        Memory watches your conversations with the assistant and distills them
        into searchable knowledge the background agents can consult. It needs an
        embedding provider — pick one that has a key configured.
      </p>

      <!-- Candidates list -->
      <div v-if="candidates.length" class="provider-grid">
        <div v-for="p in candidates" :key="p.provider"
             class="provider-row"
             :class="{ selected: selected === p.provider, disabled: !p.has_key }"
             @click="pickProvider(p)">
          <div>
            <div class="p-name">
              {{ p.provider }}
              <span v-if="!p.has_key" class="p-badge">needs key</span>
            </div>
            <div class="p-model">
              {{ p.model }}
              <template v-if="p.has_key">
                · <span class="p-key-ok">{{ p.key_hint }}</span>
              </template>
            </div>
            <div v-if="!p.has_key" class="p-nokey-hint">
              Configure in Settings → Embedding
            </div>
          </div>
          <svg v-if="selected === p.provider" class="check"
               viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="4 12 10 18 20 6"/>
          </svg>
        </div>
      </div>

      <!-- Model selector (after picking a provider) -->
      <div v-if="selected && selModels.length > 1" class="model-pick">
        <label class="mp-label">Model</label>
        <select v-model="selectedModel" class="mp-select">
          <option v-for="m in selModels" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>

      <!-- All candidates missing keys: go configure -->
      <div v-if="candidates.length && !candidates.some(c => c.has_key)" class="no-keys-msg">
        <p>None of the embedding providers have a key yet.</p>
        <button class="go-settings" @click="goToEmbeddingSettings()">
          Open Embedding Settings →
        </button>
      </div>

      <!-- One-way-door warning -->
      <div v-if="candidates.some(c => c.has_key)" class="setup-warn">
        Once memories are stored the embedding provider can't be changed — a
        different model produces vectors in a different space, where nothing
        already written is findable. To switch, first delete all memories.
      </div>

      <button v-if="candidates.some(c => c.has_key)"
              class="setup-btn"
              :disabled="!selected || saving"
              @click="enableMemory">
        {{ saving ? "Saving…" : "Enable Memory" }}
      </button>
    </div>

    <!-- ===== C. Memory list (enabled + configured) ===== -->
    <template v-else-if="isList">
      <!-- Toolbar: count on left, embedder + toggle on right -->
      <div class="mem-toolbar">
        <span class="mem-toolbar-label">
          {{ store.memory.memos.length }} memor{{ store.memory.memos.length === 1 ? 'y' : 'ies' }}
          <template v-if="store.memory.embedding">
            （{{ store.memory.embedding.provider }} / {{ store.memory.embedding.model }}）
          </template>
        </span>
        <div class="toggle" :class="{ on: store.memory.enabled }"
             title="Enable / disable auto-extraction"
             @click="onToggleMemory">
          <span class="slider"></span>
        </div>
      </div>

      <!-- Search — full-width -->
      <div class="center-header">
        <div class="search-wrap">
          <input class="search-input" type="text"
                 v-model="store.memory.query"
                 placeholder="Search memories…"
                 @input="onSearchInput" />
        </div>
      </div>

      <!-- List / empty -->
      <div class="item-list">
        <div v-if="store.memory.memos.length" class="cards">
          <div class="cards-header">
            <button class="mem-delete-all" title="Delete all memories"
                    @click="forgetMemories()">
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
              Delete All
            </button>
          </div>
          <div v-for="m in store.memory.memos" :key="m.id" class="mem-card">
            <div class="mem-body">
              <!-- View mode -->
              <div v-if="editingId !== m.id" class="mem-text">
                {{ m.content }}
                <div class="mem-footer">{{ fmtTime(m.created) }}</div>
              </div>
              <!-- Edit mode -->
              <textarea v-else class="mem-edit"
                        v-model="editText"
                        rows="3"
                        @keydown="onEditKey($event, m.id)">
              </textarea>
              <div v-if="editingId === m.id" class="edit-hint">
                Esc to cancel · Cmd+Enter to save
              </div>
            </div>
            <div v-if="editingId !== m.id" class="mem-actions">
              <button title="Edit" @click="startEdit(m)" v-html="SVG_EDIT"></button>
              <button class="del" title="Delete" @click="deleteMemo(m.id)" v-html="SVG_TRASH"></button>
            </div>
          </div>
        </div>

        <!-- Empty list: agent is learning but nothing to show yet -->
        <div v-else class="empty-state">
          <div class="e-icon">
            <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.5">
              <ellipse cx="12" cy="5" rx="9" ry="3"/>
              <path d="M3 5v14a9 3 0 0 0 18 0V5"/>
            </svg>
          </div>
          <div class="e-title">Nothing yet</div>
          <div class="e-sub">
            The agent starts extracting knowledge after your first conversation.
            Come back in a few minutes.
          </div>
        </div>
      </div>

    </template>

  </div>
</template>

<style scoped>
.viewer { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.viewer.list { background: var(--bg-editor); }

/* ---- Setup card ----------------------------------------------------------- */
.setup-card {
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 10px; padding: 24px; max-width: 480px; margin: 40px auto;
  flex-shrink: 0;
}
.setup-card h2 { font: 600 15px var(--sans); color: var(--text); margin-bottom: 6px; }
.setup-desc { font: 400 12px var(--sans); color: var(--text-4); line-height: 1.6; margin-bottom: 18px; }

.provider-grid { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.provider-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; background: var(--bg-hover); border: 1px solid var(--border);
  border-radius: 8px; cursor: pointer; transition: border-color .15s;
}
.provider-row:hover { border-color: var(--border-soft); }
.provider-row.selected { border-color: var(--brand); background: var(--wash-brand); }
.provider-row.disabled { opacity: .45; cursor: default; }
.provider-row.disabled:hover { border-color: var(--border); }
.p-name { font: 500 13px var(--sans); color: var(--text-2); display: flex; align-items: center; gap: 8px; }
.p-badge {
  font: 500 9px var(--mono); padding: 2px 6px; border-radius: 3px;
  background: var(--tint-amber); color: var(--amber);
}
.p-model { font: 400 10px var(--mono); color: var(--text-4); margin-top: 2px; }
.p-nokey-hint {
  margin-top: 4px; font: 400 10px var(--sans); color: var(--amber);
}
.p-key-ok { color: var(--text-4); }
.check { color: var(--brand); width: 16px; height: 16px; flex-shrink: 0; }

.no-keys-msg { margin-bottom: 14px; }
.no-keys-msg p { font: 400 12px var(--sans); color: var(--text-4); line-height: 1.6; }
.go-settings {
  margin-top: 10px; cursor: pointer;
  font: 500 10.5px var(--mono); color: var(--text-2);
  background: var(--bg-panel); border: 1px solid var(--border);
  padding: 6px 16px; transition: border-color .15s, color .15s;
}
.go-settings:hover { border-color: var(--brand); color: var(--brand); }

/* Model picker after selecting provider */
.model-pick { margin-bottom: 14px; }
.mp-label { display: block; font: 500 10.5px var(--mono); color: var(--text-3); margin-bottom: 4px; }
.mp-select {
  width: 100%; padding: 7px 10px;
  background: var(--bg-hover); border: 1px solid var(--border);
  color: var(--text-2); font: 400 12px var(--mono);
  border-radius: 6px; outline: none; cursor: pointer;
}
.mp-select:focus { border-color: var(--brand); }

.setup-warn {
  margin-top: 14px; padding: 10px 12px; background: var(--tint-amber);
  border-radius: 6px; font: 400 11px var(--sans); color: var(--amber); line-height: 1.5;
}
.setup-btn {
  margin-top: 16px; width: 100%; padding: 10px; background: var(--brand);
  color: var(--on-brand); border: none; border-radius: 8px;
  font: 600 13px var(--sans); cursor: pointer;
}
.setup-btn:hover { filter: brightness(1.1); }
.setup-btn:disabled { opacity: .4; cursor: default; filter: none; }

/* ---- Search header -------------------------------------------------------- */
.center-header {
  padding: 14px 20px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center;
}
.search-wrap { flex: 1; }
.search-input {
  background: var(--bg-hover); border: 1px solid var(--border);
  color: var(--text-2); font: 400 12px var(--sans); padding: 6px 10px;
  border-radius: 6px; outline: none; width: 100%;
}
.search-input:focus { border-color: var(--text-4); }
.search-input::placeholder { color: var(--text-4); }

/* ---- Memory cards --------------------------------------------------------- */
.item-list { flex: 1; overflow-y: auto; padding: 8px 20px; }
.cards { display: flex; flex-direction: column; gap: 6px; }
.cards-header {
  display: flex; justify-content: flex-end;
  padding-bottom: 6px;
}
.mem-card {
  padding: 12px 14px; background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 8px; transition: border-color .15s;
  display: flex; align-items: flex-start; gap: 12px;
}
.mem-card:hover { border-color: var(--border-soft); }
.mem-body { flex: 1; min-width: 0; }
.mem-text {
  font: 400 12.5px var(--sans); color: var(--text-2); line-height: 1.55;
  white-space: pre-wrap; word-break: break-word;
}
.mem-footer { font: 400 9.5px var(--mono); color: var(--text-4); margin-top: 6px; }

/* Inline edit */
.mem-edit {
  width: 100%; background: var(--bg-hover); border: 1px solid var(--border);
  color: var(--text); font: 400 12.5px var(--sans); line-height: 1.55;
  padding: 8px 10px; border-radius: 6px; resize: vertical; outline: none;
}
.mem-edit:focus { border-color: var(--brand); }
.edit-hint { font: 400 9px var(--mono); color: var(--text-4); margin-top: 4px; }

/* Hover actions */
.mem-actions { display: flex; gap: 2px; opacity: 0; transition: opacity .15s; flex-shrink: 0; }
.mem-card:hover .mem-actions { opacity: 1; }
.mem-actions button {
  width: 24px; height: 24px; display: flex; align-items: center; justify-content: center;
  border: none; background: none; border-radius: 4px; cursor: pointer; color: var(--text-4);
}
.mem-actions button:hover { background: var(--bg-raise); color: var(--text-2); }
.mem-actions button.del:hover { background: rgba(235,54,28,.12); color: var(--red); }
.mem-actions button :deep(svg) { width: 13px; height: 13px; }

/* ---- Empty state ---------------------------------------------------------- */
.empty-state {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 40px; text-align: center;
}
.fb-spin {
  width: 22px; height: 22px; border-radius: 50%;
  border: 2px solid var(--border); border-top-color: var(--brand);
  animation: fb-rot 0.7s linear infinite;
}
@keyframes fb-rot { to { transform: rotate(360deg); } }
.e-icon { color: var(--text-4); margin-bottom: 16px; }
.e-title { font: 600 15px var(--sans); color: var(--text-2); margin-bottom: 6px; }
.e-sub { font: 400 12px var(--sans); color: var(--text-4); max-width: 360px; line-height: 1.6; }

/* Enable button inside the off state */
.enable-btn {
  margin-top: 20px; padding: 8px 24px;
  background: var(--brand); color: var(--on-brand);
  border: none; border-radius: 6px;
  font: 600 12px var(--sans); cursor: pointer;
  transition: filter .15s;
}
.enable-btn:hover { filter: brightness(1.1); }

/* ---- Memory toolbar (list header) ---------------------------------------- */
.mem-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 20px; border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
}
.mem-toolbar-label { font: 400 11px var(--mono); color: var(--text-4); }

.mem-delete-all {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 10px;
  background: none; border: 1px solid var(--border); border-radius: 4px;
  font: 400 10.5px var(--mono); color: var(--text-4); cursor: pointer;
  transition: color .15s, border-color .15s, background .15s;
}
.mem-delete-all:hover { color: var(--red); border-color: var(--red); background: rgba(235,54,28,.08); }

/* Toggle (matches MemoryPanel, now self-contained in the viewer) */
.toggle { position: relative; width: 30px; height: 17px; flex-shrink: 0; cursor: pointer; }
.toggle .slider {
  position: absolute; cursor: pointer; inset: 0; background: var(--border-soft);
  border-radius: 3px; transition: .25s;
}
.toggle .slider::before {
  content: ""; position: absolute; height: 11px; width: 11px; left: 3px; top: 3px;
  background: var(--text); border-radius: 2px; transition: .25s;
}
.toggle.on .slider { background: var(--brand); }
.toggle.on .slider::before { transform: translateX(13px); background: var(--on-brand); }
</style>
