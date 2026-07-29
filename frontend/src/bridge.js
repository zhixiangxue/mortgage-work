/* Window-global registry. Two consumers:
   1. The Python side — native menu actions call these via evaluate_js()
      (showToast / goHome / switchView / togglePanel / focusChat / setModel).
   2. v-html mock content (doc pages, chat threads) whose inline onclick
      handlers can only resolve globals — same contract as the pre-Vue page. */
import {
  store, showToast, switchView, closeClient, togglePanel, focusChat,
  setModel, openDoc,
} from "./store.js";
import { MODEL_CATALOG, modelItemsHtml } from "./mocks/catalog.js";

/* ---- Per-message actions injected by ChatPanel's decorator ---- */

function copyMsg(btn) {
  const text = btn.closest(".msg").querySelector(".bubble").innerText;
  navigator.clipboard && navigator.clipboard.writeText(text);
  showToast("Copied to clipboard");
}

function delMsg(btn) {
  btn.closest(".msg").remove();
  showToast("Message deleted (demo)");
}

/* ---- Models settings page (DOM-driven; the page itself is v-html mock) ---- */

function provCheck(btn) {
  const head = btn.closest(".prov-head");
  const st = head.querySelector(".pstatus");
  const ck = head.querySelector(".pchecked");
  st.className = "pstatus unk";
  st.textContent = "● CHECKING…";
  // Status is only probed on demand; fake the round trip for the demo
  setTimeout(() => {
    st.className = "pstatus ok";
    st.textContent = "● CONNECTED";
    ck.textContent = "checked just now";
  }, 900);
}

function provRemove(btn, name) {
  btn.closest(".prov").remove();
  showToast(`Provider removed: ${name} (demo)`);
}

function toggleAddModel() {
  const f = document.getElementById("add-form");
  if (f) f.classList.toggle("hidden");
  closeFormDds();
}

/* ---- Add-form dropdowns (v-html DOM, same .dd look as the modal) ---- */

function closeFormDds() {
  document.querySelectorAll("#add-form .dd-menu").forEach(m => m.classList.add("hidden"));
}

function ddToggle(btn, e) {
  e.stopPropagation();
  const menu = btn.nextElementSibling;
  const wasHidden = menu.classList.contains("hidden");
  closeFormDds();
  if (wasHidden) menu.classList.remove("hidden");
}

/* Provider drives the rest: model list re-rendered, base URL prefilled */
function pickProvider(item) {
  const name = item.textContent;
  document.getElementById("nm-provider").textContent = name;
  document.getElementById("nm-url").value = MODEL_CATALOG[name].url;
  document.getElementById("nm-model-menu").innerHTML = modelItemsHtml(name);
  syncModelLabel();
  closeFormDds();
}

/* Multi-select: clicking an item toggles it, the menu stays open */
function pickModel(item, e) {
  e.stopPropagation();
  item.classList.toggle("sel");
  syncModelLabel();
}

function selectedModels() {
  return [...document.querySelectorAll("#nm-model-menu .dd-item.sel")].map(i => i.textContent);
}

function syncModelLabel() {
  const sel = selectedModels();
  document.getElementById("nm-model").textContent =
    sel.length === 0 ? "Select models…"
    : sel.length <= 2 ? sel.join(", ")
    : `${sel[0]} +${sel.length - 1} more`;
}

/* Flip the default switch: exactly one model is default at a time */
function setDefaultModel(sw, model) {
  if (sw.closest(".mrow").classList.contains("off")) {
    showToast("Enable the model first");
    return;
  }
  document.querySelectorAll(".mrow").forEach(r => r.classList.remove("on"));
  document.querySelectorAll(".msw").forEach(s => s.classList.remove("on"));
  sw.classList.add("on");
  sw.closest(".mrow").classList.add("on");
  setModel(model);
  showToast(`Default model: ${model}`);
}

/* Disabled models leave the composer picker; the default model is protected */
function toggleModelDisable(btn, model) {
  const row = btn.closest(".mrow");
  if (row.classList.contains("on")) {
    showToast("Set another model as default first");
    return;
  }
  const off = row.classList.toggle("off");
  btn.textContent = off ? "Enable" : "Disable";
  if (off) {
    store.models = store.models.filter(m => m !== model);
    showToast(`Model disabled: ${model}`);
  } else {
    if (!store.models.includes(model)) store.models.push(model);
    showToast(`Model enabled: ${model}`);
  }
}

function removeModel(btn, model) {
  const row = btn.closest(".mrow");
  if (row.classList.contains("on")) {
    showToast("Set another model as default first");
    return;
  }
  row.remove();
  store.models = store.models.filter(m => m !== model);
  showToast(`Model removed: ${model} (demo)`);
}

/* Shared row template so hand-written and saved rows stay in sync */
function modelRowHtml(model) {
  return `<div class="mrow"><span class="mname">${model}</span><span class="dlbl">DEFAULT</span><span class="m-acts"><button class="btn-sm" onclick="toggleModelDisable(this, '${model}')">Disable</button><button class="btn-sm" onclick="removeModel(this, '${model}')">Remove</button></span><span class="msw" onclick="setDefaultModel(this, '${model}')"></span></div>`;
}

function saveNewModel() {
  const name = document.getElementById("nm-provider").textContent;
  const models = selectedModels();
  if (!models.length) { showToast("Pick at least one model"); return; }
  // Same provider already configured → merge into its card, no duplicate blocks
  let existing = [...document.querySelectorAll("#prov-list .prov")]
    .find(p => p.querySelector(".pname").textContent === name);
  if (!existing) {
    existing = document.createElement("div");
    existing.className = "prov";
    existing.innerHTML = `<div class="prov-head">
      <span class="pname">${name}</span>
      <span class="pstatus unk">● UNCHECKED</span>
      <span class="pchecked">never checked</span>
      <span class="pactions"><button class="btn-sm" onclick="provCheck(this)">Check</button><button class="btn-sm" onclick="provRemove(this, '${name}')">Remove</button></span>
    </div>
    <div class="prov-body">
      <div class="pkey">key set · hidden</div>
    </div>`;
    document.getElementById("prov-list").appendChild(existing);
  }
  const body = existing.querySelector(".prov-body");
  const have = [...body.querySelectorAll(".mname")].map(n => n.textContent);
  const added = models.filter(m => !have.includes(m));
  if (!added.length) { showToast(`${name} · already configured`); return; }
  body.insertAdjacentHTML("beforeend", added.map(modelRowHtml).join(""));
  // New models become available in the composer picker right away
  added.forEach(m => { if (!store.models.includes(m)) store.models.push(m); });
  toggleAddModel();
  showToast(`Models added: ${added.join(", ")} (demo)`);
}

export function registerGlobals() {
  Object.assign(window, {
    // Python menu hooks
    showToast,
    toastMsg: showToast,
    goHome: closeClient,
    switchView,
    togglePanel,
    focusChat,
    setModel,
    // v-html inline handlers
    openDoc,
    copyMsg,
    delMsg,
    provCheck,
    provRemove,
    toggleAddModel,
    ddToggle,
    pickProvider,
    pickModel,
    setDefaultModel,
    toggleModelDisable,
    removeModel,
    saveNewModel,
  });
  // Any outside click closes the add-form dropdowns (v-html, no Vue refs here)
  document.addEventListener("click", closeFormDds);
}
