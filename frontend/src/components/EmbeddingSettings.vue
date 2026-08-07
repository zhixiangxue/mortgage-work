<script setup>
/* Settings — Embedding. A lightweight view over the same models.yaml that
   LLM uses, filtered to the three providers that serve embeddings. The
   heavy provider management (add/edit/remove models, check connectivity)
   lives under LLM; here the LO just adds API keys so memory has something
   to pick from. */
import { ref, computed, onMounted } from "vue";
import { store, showToast,
         loadModels, loadMemoryConfig,
         saveProvider } from "../store.js";

/* Mirror of model_settings.EMBEDDING_CAPABLE — the three providers that
   can embed. The list is short enough to hard-code; when seeka or chak
   grows a new embedder we'll move it to the bridge. */
const EMBEDDERS = [
  { provider: "openai",  label: "OpenAI",  model: "text-embedding-3-small" },
  { provider: "azure",   label: "Azure",   model: "text-embedding-3-small" },
  { provider: "bailian", label: "阿里百炼", model: "text-embedding-v3" },
];

/* Which embedders already have keys (from store.memory.candidates) and
   which are missing. */
const hasKey = (p) => (store.memory.candidates || [])
  .some(c => c.provider === p.provider);

/* Currently selected embedder for memory */
const isSelected = (p) => store.memory.embedding
  && store.memory.embedding.provider === p.provider;

/* Inline add form */
const adding = ref(false);
const form = ref({ provider: "openai", api_key: "" });
const saving = ref(false);
const formError = ref("");

function openAdd() {
  const missing = EMBEDDERS.filter(e => !hasKey(e));
  if (!missing.length) return;
  form.value = { provider: missing[0].provider, api_key: "" };
  formError.value = "";
  adding.value = true;
}

async function doSave() {
  if (!form.value.api_key.trim()) {
    formError.value = "Paste an API key";
    return;
  }
  saving.value = true;
  formError.value = "";
  const emb = EMBEDDERS.find(e => e.provider === form.value.provider);
  try {
    const res = await saveProvider({
      provider: form.value.provider,
      base_url: "",
      api_key: form.value.api_key.trim(),
      models: emb ? [emb.model] : [],
    });
    if (!res || res.error) {
      formError.value = (res && res.error) || "could not save";
    } else {
      adding.value = false;
      showToast(`${emb ? emb.label : form.value.provider} key saved`);
      // Refresh both lists: the providers block changed, and memory may
      // now have a new candidate to pick from.
      await loadModels();
      await loadMemoryConfig();
    }
  } finally { saving.value = false; }
}

onMounted(() => { loadMemoryConfig(); });
</script>

<template>
  <div id="doc-area">
    <div class="md-doc">
      <h1>Embedding
        <button class="btn-sm primary" style="margin-left:auto"
                @click="openAdd()"
                :disabled="EMBEDDERS.every(e => hasKey(e))">
          Add Key
        </button>
      </h1>
      <p class="path-line">
        Embedding turns conversation text into searchable vectors. Memory picks
        one of these providers to do that work — the key lives in the same
        <a @click="() => {}">models.yaml</a> as your LLM providers but is kept
        separate here so the two concerns don't blur.
      </p>

      <!-- Inline add form: just provider + key. Model is auto-selected. -->
      <div v-if="adding" class="add-form">
        <div>
          <label>Provider</label>
          <select v-model="form.provider" class="sel">
            <option v-for="e in EMBEDDERS.filter(e => !hasKey(e))"
                    :key="e.provider" :value="e.provider">
              {{ e.label }}
            </option>
          </select>
        </div>
        <div class="full">
          <label>API Key</label>
          <input v-model="form.api_key" type="password" placeholder="sk-…">
        </div>
        <p v-if="formError" class="form-err">
          {{ formError }}
          <button type="button" class="x" @click="formError = ''">dismiss</button>
        </p>
        <div class="apply-row full">
          <button class="btn-sm primary" @click="doSave()"
                  :disabled="saving">
            {{ saving ? "Saving…" : "Save" }}
          </button>
          <button class="btn-sm" @click="adding = false">Cancel</button>
        </div>
      </div>

      <h2>Providers</h2>

      <div v-for="e in EMBEDDERS" :key="e.provider" class="prov"
           :class="{ selected: isSelected(e) }">
        <div class="prov-head">
          <span class="pname">{{ e.label }}</span>
          <span v-if="isSelected(e)" class="pstatus ok">● IN USE</span>
          <span v-if="hasKey(e)" class="pchecked">{{ e.model }}</span>
          <span v-else class="pstatus err">no key</span>
        </div>
        <div class="prov-body">
          <div class="pkey">
            <template v-if="hasKey(e)">
              {{ (store.memory.candidates.find(c => c.provider === e.provider) || {}).key_hint || "key set" }}
            </template>
            <template v-else>
              No API key — memory can't use this provider until one is added.
            </template>
          </div>
        </div>
      </div>

      <div v-if="!store.memory.embedding" class="empty" style="margin-top: 16px">
        No embedder selected yet. Open the Memory tab to pick one — once
        memories are stored the choice is locked, so choose carefully.
      </div>
    </div>
  </div>
</template>

<style scoped>
/* These match the ModelSettings styles — the .prov / .add-form / .btn-sm
   blocks live in global.css, so only embedding-specific overrides here. */
.path-line { margin: 14px 0 4px; font: 400 11px var(--mono); color: var(--text-4); }
.path-line a { color: var(--brand); cursor: pointer; margin-left: 8px; }
.prov.selected { border-color: var(--brand); }
.pstatus.ok { color: var(--brand); }
.pstatus.err { color: var(--amber); }
.pkey { display: flex; gap: 14px; }
.pchecked { font: 400 11px var(--mono); color: var(--text-4); }
.sel {
  padding: 7px 9px; background: var(--bg); border: 1px solid var(--border);
  color: var(--text); font: 400 11px var(--mono); outline: none; width: 100%;
}
.sel:focus { border-color: var(--brand); }
.form-err { margin: 0; font: 400 11px var(--mono); color: var(--red); }
.form-err .x {
  margin-left: 8px; background: none; border: none; cursor: pointer;
  font: 400 11px var(--mono); color: var(--text-4); text-decoration: underline;
}
.form-err .x:hover { color: var(--text-2); }
.empty {
  border: 1px dashed var(--border-soft); padding: 16px;
  font: 400 11.5px/1.7 var(--mono); color: var(--text-4);
}
</style>
