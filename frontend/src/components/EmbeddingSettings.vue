<script setup>
/* Settings — Embedding. Key editing is inline: click Edit, paste the key,
   hit Save. Available models are shown as text — the Memory tab picks which
   model to use, this page just configures the provider. */
import { ref, onMounted } from "vue";
import { store, showToast,
         loadEmbeddingProviders,
         saveEmbeddingProvider } from "../store.js";

const EMBEDDERS = [
  { provider: "openai",  label: "OpenAI" },
  { provider: "bailian", label: "Alibaba Bailian" },
];

const embedProvs = () => store.memory.embedProviders || {};

const hasKey = (p) => {
  const ep = embedProvs()[p.provider];
  return ep ? ep.has_key : false;
};

const editing = ref("");
const editKey = ref("");
const editError = ref("");
const saving = ref(false);

function startEdit(e) {
  editing.value = e.provider;
  editKey.value = "";
  editError.value = "";
}

function cancelEdit() {
  editing.value = "";
  editKey.value = "";
  editError.value = "";
}

async function doSave(e) {
  if (!editKey.value.trim()) {
    editError.value = "Paste an API key";
    return;
  }
  saving.value = true;
  editError.value = "";
  try {
    const res = await saveEmbeddingProvider(e.provider, editKey.value.trim());
    if (!res || res.error) {
      editError.value = (res && res.error) || "could not save";
    } else {
      editing.value = "";
      showToast(`${e.label} key saved`);
      await loadEmbeddingProviders();
    }
  } finally { saving.value = false; }
}

onMounted(() => { loadEmbeddingProviders(); });
</script>

<template>
  <div id="doc-area">
    <div class="md-doc">
      <h1>Embedding</h1>
      <p class="path-line">
        Embedding turns conversation text into searchable vectors. Memory picks
        one of these providers to do that work.
      </p>

      <h2>Providers</h2>

      <div v-for="e in EMBEDDERS" :key="e.provider" class="prov"
           :class="{ editing: editing === e.provider }">
        <div class="prov-head">
          <span class="pname">{{ e.label }}</span>
          <span class="pstatus" :class="hasKey(e) ? 'ok' : 'err'">
            {{ hasKey(e) ? 'key set' : 'no key' }}
          </span>
          <span class="pactions">
            <button v-if="editing !== e.provider" class="btn-sm" @click="startEdit(e)">Edit</button>
            <template v-else>
              <button class="btn-sm primary" @click="doSave(e)" :disabled="saving">
                {{ saving ? "Saving…" : "Save" }}
              </button>
              <button class="btn-sm" @click="cancelEdit">Cancel</button>
            </template>
          </span>
        </div>
        <div class="prov-body">
          <!-- Key row -->
          <div class="pkey" v-if="editing !== e.provider">
            <template v-if="hasKey(e)">
              {{ (embedProvs()[e.provider] || {}).key_hint || "key set" }}
            </template>
            <template v-else>
              No API key — add one to use this provider.
            </template>
          </div>
          <div class="pkey edit-key" v-else>
            <input v-model="editKey" type="password" placeholder="sk-…" class="key-inp">
            <p v-if="editError" class="form-err">{{ editError }}</p>
          </div>
          <!-- Models list -->
          <div class="models-inline">
            <span v-for="m in (embedProvs()[e.provider] || {}).available_models || []" :key="m" class="mtag">{{ m }}</span>
          </div>
        </div>
      </div>

      <div v-if="!store.memory.embedActive" class="empty" style="margin-top: 16px">
        No embedder selected yet. Open the Memory tab to pick one — once
        memories are stored the choice is locked, so choose carefully.
      </div>
    </div>
  </div>
</template>

<style scoped>
.path-line { margin: 14px 0 4px; font: 400 11px var(--mono); color: var(--text-4); }
.path-line a { color: var(--brand); cursor: pointer; margin-left: 8px; }
.prov.editing { border-color: var(--brand); }
.pstatus.err { color: var(--amber); }
.edit-key { display: flex; flex-direction: column; gap: 6px; }
.edit-key .key-inp {
  padding: 5px 8px; background: var(--bg); border: 1px solid var(--border);
  color: var(--text); font: 400 11px var(--mono); outline: none; width: 100%;
  border-radius: 4px;
}
.edit-key .key-inp:focus { border-color: var(--brand); }
/* Models — inline tags, same look as LLM tab */
.models-inline { display: flex; flex-wrap: wrap; gap: 8px; padding: 10px 12px; }
.mtag {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 9px; border: 1px solid var(--border);
  font: 400 11px var(--mono); color: var(--text-2);
}
.form-err { margin: 0; font: 400 11px var(--mono); color: var(--red); }
.empty {
  border: 1px dashed var(--border-soft); padding: 16px;
  font: 400 11.5px/1.7 var(--mono); color: var(--text-4);
}
</style>
