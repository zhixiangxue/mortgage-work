<script setup>
/* Settings — models. A view over ~/MortgageWork/settings/models.yaml, which is
   the only place model config lives: no database, no network, nothing in the
   repo. Every button here is a bridge call that rewrites that file and gets the
   new contents back, so this pane can't show something the file doesn't say.

   Deliberately small: a provider can be edited (keys get rotated and typo'd),
   checked, or removed; a model can only be removed. Which model you're talking
   to right now is the composer's business, not the config file's. */
import { reactive, ref, computed, onMounted, onUnmounted } from "vue";
import {
  store, askThen, loadModels, saveProvider, removeProvider,
  removeModel, checkProvider, revealModelsFile,
} from "../store.js";
import { CATALOG, catalogEntry, providerLabel } from "../catalog.js";

/* Check results are per-session, not persisted: a "connected 2h ago" badge
   read back from disk would be a claim about the network, and the network
   moved on. Unchecked is the honest default every time the tab opens. */
const checks = reactive({});

const form = reactive({
  open: false,
  editing: false,       // true = provider is locked, empty key means "keep it"
  provider: "openai",
  base_url: "",
  api_key: "",
  error: "",            // save failure, shown red inside the box (not a toast)
});
const selected = ref([]); // chosen model names — the source of truth for save
const custom = ref("");   // typed-in name for a model the catalog doesn't list
const dd = ref("");       // open provider dropdown: "" | "provider"
const menuOpen = ref("");  // which provider's "⋮" menu is open

const entry = computed(() => catalogEntry(form.provider));
// Chips to show: the catalog shortlist, plus anything already picked that the
// catalog doesn't carry (a local model tag, a hand-edited entry).
const chips = computed(() => {
  const cat = (entry.value && entry.value.models) || [];
  return [...cat, ...selected.value.filter(m => !cat.includes(m))];
});

// The file may have been edited by hand (or by another window) since boot
onMounted(() => {
  loadModels();
  document.addEventListener("click", closeAll);
});
onUnmounted(() => { document.removeEventListener("click", closeAll); clearError(); });

function closeAll() { dd.value = ""; menuOpen.value = ""; }
function toggleDd(which, e) {
  e.stopPropagation();
  dd.value = dd.value === which ? "" : which;
}

function toggleMenu(provider, e) {
  e.stopPropagation();
  menuOpen.value = menuOpen.value === provider ? "" : provider;
}
function closeMenu() { menuOpen.value = ""; }

function doAction(action, p) {
  closeMenu();
  if (action === "check") check(p);
  else if (action === "edit") openEdit(p);
  else if (action === "remove") askRemoveProvider(p);
}

/* Errors linger 30s then clear themselves, or the user closes them — long
   enough to read and act on, unlike a toast that's gone before you look up. */
let errTimer = null;
function setError(msg) {
  form.error = msg;
  clearTimeout(errTimer);
  if (msg) errTimer = setTimeout(() => { form.error = ""; }, 30000);
}
function clearError() { form.error = ""; clearTimeout(errTimer); }

function openAdd() {
  // Default to something not configured yet — re-adding OpenAI is the rare case
  const fresh = CATALOG.find(c => !store.providers.some(p => p.provider === c.id));
  Object.assign(form, { open: true, editing: false, api_key: "" });
  clearError();
  pickProvider((fresh || CATALOG[0]).id);
}

function openEdit(p) {
  Object.assign(form, {
    open: true, editing: true, provider: p.provider,
    base_url: p.base_url, api_key: "",
  });
  selected.value = [...p.models];
  custom.value = "";
  clearError();
  closeDd();
}

function pickProvider(id) {
  form.provider = id;
  const c = catalogEntry(id);
  // Local runtimes have no default endpoint in chak, so theirs is prefilled;
  // for hosted providers an empty field means "use chak's default".
  form.base_url = c && c.needsUrl ? c.url : "";
  selected.value = [];
  custom.value = "";
  closeDd();
}

// Click a chip to add/remove the model — that's the whole interaction.
function toggleModel(m) {
  const i = selected.value.indexOf(m);
  if (i >= 0) selected.value.splice(i, 1);
  else selected.value.push(m);
}

// A model name the catalog doesn't list (local tags especially) — Enter adds it
function addCustom() {
  const m = custom.value.trim();
  if (m && !selected.value.includes(m)) selected.value.push(m);
  custom.value = "";
}

function save() {
  if (!selected.value.length) { setError("Pick at least one model"); return; }
  clearError();
  const provider = form.provider;
  saveProvider({
    provider,
    base_url: form.base_url.trim(),
    api_key: form.api_key.trim(),
    models: [...selected.value],
  }).then(res => {
    if (res.ok) { form.open = false; check({ provider }); }
    else setError(res.error);
  });
}

function check(p) {
  checks[p.provider] = { state: "checking" };
  checkProvider(p.provider).then(res => {
    checks[p.provider] = res.ok
      ? { state: "ok", note: res.note || `answered as ${res.model}` }
      : { state: "fail", note: res.reason || "check failed" };
    if (!res.ok && res.detail) console.warn(`[models] ${p.provider}: ${res.detail}`);
  });
}

function askRemoveProvider(p) {
  // The only irreversible button on this pane: the key goes with the provider
  askThen(`Remove ${providerLabel(p.provider)}?`,
          `Its API key is deleted from models.yaml. You'll have to paste it again to come back.`,
          "Remove provider", () => removeProvider(p.provider));
}

/* A live check this session wins; otherwise fall back to what's stored in the
   file. A persisted result is always shown with when it happened — "connected
   2h ago" is a fact about the past, not a promise the network is up right now. */
function relTime(ts) {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function statusOf(p) {
  const live = checks[p.provider];
  if (live) {
    if (live.state === "checking") return { cls: "unk", label: "● CHECKING…", note: "" };
    if (live.state === "ok") return { cls: "ok", label: "● CONNECTED", note: live.note || "just now" };
    return { cls: "err", label: "● FAILED", note: live.note || "" };
  }
  const lc = p.last_check;
  if (lc) {
    return lc.ok
      ? { cls: "ok", label: "● CONNECTED", note: `checked ${relTime(lc.at)}` }
      : { cls: "err", label: "● FAILED", note: `${lc.note || "check failed"} · ${relTime(lc.at)}` };
  }
  return { cls: "unk", label: "● UNCHECKED", note: "" };
}
</script>

<template>
  <div id="doc-area">
    <div class="md-doc">
      <h1>LLM
        <button class="btn-sm primary" style="margin-left:auto" @click="openAdd()">Add Provider</button>
      </h1>
      <p class="path-line">
        Your API keys are kept on this computer only — never uploaded or synced.
        <a @click="revealModelsFile()">show file</a>
      </p>

      <!-- Add / Edit: one form, because the fields are the same either way.
           The provider is fixed while editing — a different provider is a
           different entry in the file, not a rename. -->
      <div v-if="form.open" class="add-form">
        <div>
          <label>Provider</label>
          <div v-if="form.editing" class="locked">{{ providerLabel(form.provider) }}</div>
          <div v-else class="dd">
            <button class="dd-btn" @click="toggleDd('provider', $event)">
              <span>{{ providerLabel(form.provider) }}</span><span class="arr">▼</span>
            </button>
            <div class="dd-menu" v-show="dd === 'provider'">
              <div v-for="c in CATALOG" :key="c.id" class="dd-item"
                   :class="{ sel: c.id === form.provider }" @click="pickProvider(c.id)">{{ c.label }}</div>
            </div>
          </div>
        </div>
        <div>
          <label>Base URL</label>
          <input v-model="form.base_url" :placeholder="entry ? entry.url : 'provider default'">
        </div>
        <div class="full">
          <label>Models</label>
          <!-- Just the models this provider offers — click to pick, click to
               drop. The typed field below is only for a name not in the list. -->
          <div class="chips">
            <button v-for="m in chips" :key="m" type="button"
                    class="chip" :class="{ on: selected.includes(m) }"
                    @click="toggleModel(m)">{{ m }}</button>
            <span v-if="!chips.length" class="chips-empty">No preset models — add one below.</span>
          </div>
          <div class="chip-add">
            <input v-model="custom" @keydown.enter.prevent="addCustom()"
                   placeholder="another model name">
            <button class="btn-sm" type="button" @click="addCustom()">Add</button>
          </div>
        </div>
        <div class="full">
          <label>API Key</label>
          <input v-model="form.api_key" type="password"
                 :placeholder="form.editing ? 'leave empty to keep the current key' : 'sk-…'">
        </div>
        <!-- Save errors: quiet red text, dismissable, gone after 30s — enough
             to notice and read without shouting like a boxed alert. -->
        <p v-if="form.error" class="form-err full">
          {{ form.error }}
          <button type="button" class="x" @click="clearError()">dismiss</button>
        </p>
        <div class="apply-row full">
          <button class="btn-sm primary" @click="save()">Save</button>
          <button class="btn-sm" @click="form.open = false">Cancel</button>
        </div>
      </div>

      <h2>Providers</h2>
      <div v-if="!store.providers.length" class="empty">
        Nothing configured yet. Add a provider and its models become available in
        the chat panel's model picker.
      </div>
      <div v-for="p in store.providers" :key="p.provider" class="prov"
           :class="{ editing: form.open && form.editing && form.provider === p.provider }">
        <div class="prov-head">
          <span class="pname">{{ providerLabel(p.provider) }}</span>
          <span class="pstatus" :class="statusOf(p).cls">{{ statusOf(p).label }}</span>
          <span class="pchecked">{{ statusOf(p).note }}</span>
          <span class="pactions">
            <button class="btn-sm menu-trigger" @click.stop="toggleMenu(p.provider, $event)">⋮</button>
            <div v-show="menuOpen === p.provider" class="dd-menu pactions-menu">
              <div class="dd-item" @click="doAction('check', p)">Check</div>
              <div class="dd-item" @click="doAction('edit', p)">Edit</div>
              <div class="dd-item danger" @click="doAction('remove', p)">Remove</div>
            </div>
          </span>
        </div>
        <div class="prov-body">
          <div class="pkey">
            {{ p.key_hint || "no key set" }}
            <span class="url">{{ p.base_url || "provider default endpoint" }}</span>
          </div>
          <!-- Models sit inline, not one fat row each — a trash icon fades in
               on hover, the only thing you can do to a model here. -->
          <div class="models-inline">
            <span v-if="!p.models.length" class="mtag-none">no models — Edit to add one</span>
            <span v-for="m in p.models" :key="m" class="mtag">
              {{ m }}
              <button class="mtag-del" title="Remove model" @click="removeModel(p.provider, m)">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 14h10l1-14"/>
                </svg>
              </button>
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* .prov / .add-form / .dd-* / .btn-sm live in global.css — shared with the
   New Client modal and the doc pages. Only what's specific to this pane: */
.path-line { margin: 14px 0 4px; font: 400 11px var(--mono); color: var(--text-4); }
.path-line a { color: var(--brand); cursor: pointer; margin-left: 8px; }
.pstatus.err { color: var(--red); }
.pkey { display: flex; gap: 14px; }
.pkey .url { color: var(--text-3); }
.prov.editing { border-color: var(--brand); }
/* Configured models, inline — a trash icon fades in on hover, nothing else */
.models-inline { display: flex; flex-wrap: wrap; gap: 8px; padding: 10px 12px; }
.mtag {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 9px; border: 1px solid var(--border);
  font: 400 11px var(--mono); color: var(--text-2);
}
.mtag-del {
  display: inline-flex; align-items: center; padding: 0;
  background: none; border: none; color: var(--text-4); cursor: pointer;
  opacity: 0; transition: opacity .12s;
}
.mtag:hover .mtag-del { opacity: 1; }
.mtag-del:hover { color: var(--red); }
.mtag-none { font: 400 11px var(--mono); color: var(--text-4); }
.empty {
  border: 1px dashed var(--border-soft); padding: 16px;
  font: 400 11.5px/1.7 var(--mono); color: var(--text-4);
}
.locked {
  padding: 7px 9px; border: 1px solid var(--border); background: var(--bg-raise);
  font: 400 11px var(--mono); color: var(--text-3);
}
/* Model picker — one clickable chip per model, filled when it's on */
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  padding: 6px 12px; cursor: pointer;
  border: 1px solid var(--border-soft); background: var(--bg);
  color: var(--text-2); font: 400 11px var(--mono);
}
.chip:hover { border-color: var(--brand); color: var(--text); }
.chip.on { border-color: var(--brand); background: var(--tint-green); color: var(--brand); }
.chips-empty { font: 400 11px var(--mono); color: var(--text-4); }
/* Escape hatch for a model the catalog doesn't list (local tags, new releases) */
.chip-add { display: flex; gap: 8px; margin-top: 10px; }
.chip-add input {
  flex: 1; background: var(--bg); border: 1px solid var(--border);
  color: var(--text); font: 400 11px var(--mono); padding: 7px 9px; outline: none;
}
.chip-add input:focus { border-color: var(--brand); }
/* Inline save error — quiet red text, no box; a subtle dismiss link */
.form-err { margin: 0; font: 400 11px var(--mono); color: var(--red); }
.form-err .x {
  margin-left: 8px; background: none; border: none; cursor: pointer;
  font: 400 11px var(--mono); color: var(--text-4); text-decoration: underline;
}
.form-err .x:hover { color: var(--text-2); }

/* ── "⋮" action menu ──────────────────────────────────────────────────── */
.pactions { position: relative; }
.menu-trigger {
  width: 28px; padding: 4px 0; text-align: center;
  font-size: 15px; line-height: 1; letter-spacing: 1px; color: var(--text-4);
}
.menu-trigger:hover { color: var(--text-2); }
.pactions-menu {
  right: 0; left: auto; min-width: 110px;
}
.pactions-menu .dd-item.danger { color: var(--red); }
.pactions-menu .dd-item.danger:hover { background: rgba(235,54,28,.1); }
</style>
