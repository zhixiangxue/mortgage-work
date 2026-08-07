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
         updateMemo, deleteMemo } from "../store.js";

/* ---- state ---------------------------------------------------------------- */
const selected = ref("");        // which provider row is picked
const saving = ref(false);

/* Three mutually exclusive states, derived from the store */
const isOff    = computed(() => !store.memory.enabled);
const isSetup  = computed(() => store.memory.enabled && !store.memory.embedding);
const isList   = computed(() => store.memory.enabled && !!store.memory.embedding);

/* Derived: candidates ready to display in the picker grid */
const candidates = computed(() => store.memory.candidates || []);

/* ---- setup card ----------------------------------------------------------- */
function pickProvider(p) { selected.value = p.provider; }

async function enableMemory() {
  if (!selected.value || saving.value) return;
  saving.value = true;
  try {
    await saveMemoryEmbedding(selected.value);
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

/* Ensure the config is fresh on mount. */
loadMemoryConfig();
loadMemos();
</script>

<template>
  <div class="viewer" :class="{ list: isList }">

    <!-- ===== A. Memory off ===== -->
    <div v-if="isOff" class="empty-state">
      <div class="e-icon">
        <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.5">
          <ellipse cx="12" cy="5" rx="9" ry="3"/>
          <path d="M3 5v14a9 3 0 0 0 18 0V5"/>
        </svg>
      </div>
      <div class="e-title">Memory is off</div>
      <div class="e-sub">
        Toggle it on in the sidebar to start. Once enabled, the agent will
        extract knowledge from your conversations automatically.
      </div>
    </div>

    <!-- ===== B. Setup card (enabled, no embedder) ===== -->
    <div v-else-if="isSetup" class="setup-card">
      <h2>Turn on Work Memory</h2>
      <p class="setup-desc">
        Memory watches your conversations with the assistant and distills them
        into searchable knowledge the background agents can consult. It needs an
        embedding provider — a service that turns sentences into retrievable
        vectors.
      </p>

      <!-- Candidates list -->
      <div v-if="candidates.length" class="provider-grid">
        <div v-for="p in candidates" :key="p.provider"
             class="provider-row"
             :class="{ selected: selected === p.provider }"
             @click="pickProvider(p)">
          <div>
            <div class="p-name">{{ p.provider }}</div>
            <div class="p-model">{{ p.model }} · {{ p.key_hint }}</div>
          </div>
          <svg v-if="selected === p.provider" class="check"
               viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="4 12 10 18 20 6"/>
          </svg>
        </div>
      </div>

      <!-- No candidates: guide to Settings → Embedding -->
      <div v-else class="no-candidates">
        <p>
          None of your configured providers support embeddings — or they're
          missing an API key. Add one in <strong>Settings → Embedding</strong>:
          OpenAI, Azure and 阿里百炼 all serve embeddings alongside chat.
        </p>
        <button class="go-settings" @click="goToEmbeddingSettings()">
          Open Embedding Settings →
        </button>
      </div>

      <!-- One-way-door warning -->
      <div v-if="candidates.length" class="setup-warn">
        Once memories are stored the embedding provider can't be changed — a
        different model produces vectors in a different space, where nothing
        already written is findable. To switch, first delete all memories.
      </div>

      <button v-if="candidates.length"
              class="setup-btn"
              :disabled="!selected || saving"
              @click="enableMemory">
        {{ saving ? "Saving…" : "Enable Memory" }}
      </button>
    </div>

    <!-- ===== C. Memory list (enabled + configured) ===== -->
    <template v-else-if="isList">
      <!-- Search — full-width, the only header element -->
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

      <!-- Footer: which embedder is powering this -->
      <div v-if="store.memory.embedding" class="embedding-foot">
        {{ store.memory.embedding.provider }} / {{ store.memory.embedding.model }}
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
.p-name { font: 500 13px var(--sans); color: var(--text-2); }
.p-model { font: 400 10px var(--mono); color: var(--text-4); margin-top: 2px; }
.check { color: var(--brand); width: 16px; height: 16px; flex-shrink: 0; }

.no-candidates { margin-bottom: 14px; }
.no-candidates p { font: 400 12px var(--sans); color: var(--text-4); line-height: 1.6; }
.go-settings {
  margin-top: 10px; cursor: pointer;
  font: 500 10.5px var(--mono); color: var(--text-2);
  background: var(--bg-panel); border: 1px solid var(--border);
  padding: 6px 16px; transition: border-color .15s, color .15s;
}
.go-settings:hover { border-color: var(--brand); color: var(--brand); }

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
.e-icon { color: var(--text-4); margin-bottom: 16px; }
.e-title { font: 600 15px var(--sans); color: var(--text-2); margin-bottom: 6px; }
.e-sub { font: 400 12px var(--sans); color: var(--text-4); max-width: 360px; line-height: 1.6; }

/* ---- Embedding footer ----------------------------------------------------- */
.embedding-foot {
  padding: 8px 20px; border-top: 1px solid var(--border);
  font: 400 9.5px var(--mono); color: var(--text-4);
}
</style>
