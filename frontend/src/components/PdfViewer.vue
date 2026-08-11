<script setup>
/* pdf.js viewer — virtual-scrolled via RecycleScroller so only 4-6 pages
   exist in the DOM at any time, regardless of document length. Jumping to
   page 531 is instant — the scroller knows exactly where each page sits
   without rendering the 530 pages before it.

   NO worker thread: the worker module is compiled in-tree and registered
   as a main-thread handler, avoiding the fragile dynamic-import chain that
   WKWebView trips over. Local files ≤ 40 MB render fine on one thread.

   Fillable forms (AcroForm) stay fillable: fields render as native HTML
   inputs on an AnnotationLayer above the canvas. */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import { RecycleScroller } from "vue-virtual-scroller";
import "vue-virtual-scroller/dist/vue-virtual-scroller.css";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import { WorkerMessageHandler } from "pdfjs-dist/legacy/build/pdf.worker.mjs";
import { SimpleLinkService } from "pdfjs-dist/legacy/web/pdf_viewer.mjs";
import "pdfjs-dist/legacy/web/pdf_viewer.css";
import PdfPage from "./PdfPage.vue";
import { showToast } from "../store.js";

globalThis.pdfjsWorker = { WorkerMessageHandler };

const PAGE_GAP = 18;

const props = defineProps({
  bytes: { type: Uint8Array, required: true },
  scope: { type: String, default: "" },
  path: { type: String, default: "" },
  targetPage: { type: Number, default: 0 },
  targetSeq: { type: Number, default: 0 },
});
const emit = defineEmits(["saved"]);

const scrollerRef = ref(null);        // RecycleScroller component instance
const wrapRef = ref(null);             // outer pv-wrap element for width early on
const pageNo = ref(1);
const pageCount = ref(0);
const zoom = ref(0);                   // 0 = fit width
const fallbackUrl = ref("");
const dirty = ref(false);
const saving = ref(false);

const pdf = shallowRef(null);     // PDFDocumentProxy — reactive so PdfPage re-renders when bytes change
const fitScale = ref(1);
const basePageW = ref(0);
const basePageH = ref(0);
let stallTimer = null;
const fieldObjects = shallowRef(null);   // reactive so PdfPage gets field data on reload
const linkService = new SimpleLinkService();

function currentScale() { return zoom.value || fitScale.value; }
const zoomLabel = () => Math.round((currentScale() / fitScale.value) * 100) + "%";

// --- virtual-scroller derived state ---

const pageItems = computed(() => {
  if (!pageCount.value) return [];
  return Array.from({ length: pageCount.value }, (_, i) => ({ num: i + 1 }));
});

const ITEM_HEIGHT = computed(() => {
  if (!basePageH.value) return 100; // minimum fallback: prevents "Rendered items limit reached" when scroller mounts before page 1 is measured
  return Math.round(basePageH.value * currentScale()) + PAGE_GAP;
});

const pageWidth = computed(() => {
  if (!basePageW.value) return 0;
  return Math.round(basePageW.value * currentScale());
});

const pageHeight = computed(() => {
  if (!basePageH.value) return 0;
  return Math.round(basePageH.value * currentScale());
});

// Force RecycleScroller to re-measure when zoom changes (same trick mai-app uses
// with react-virtuoso: change the key so the internal cache is rebuilt).
const scrollerKey = computed(() => `${zoom.value}-${basePageW.value}-${basePageH.value}`);

// --- scroll / page tracking ---

function onVirtualScroll() {
  const el = scrollerRef.value?.$el;
  if (!el || !ITEM_HEIGHT.value) return;
  const p = Math.max(1, Math.floor(el.scrollTop / ITEM_HEIGHT.value) + 1);
  pageNo.value = Math.min(p, pageCount.value || 1);
}

function scrollToPage(page) {
  page = Math.max(1, Math.min(page, pageCount.value || 0));
  if (!page || !scrollerRef.value) return;
  scrollerRef.value.scrollToItem(page - 1);
  pageNo.value = page;
}

// --- zoom ---

function setZoom(dir) {
  if (dir === 0) zoom.value = 0;
  else {
    const next = currentScale() * (dir > 0 ? 1.2 : 1 / 1.2);
    zoom.value = Math.min(fitScale.value * 4, Math.max(fitScale.value * 0.35, next));
  }
}

// --- save ---

const canSave = () => !!(props.scope && props.path);

async function save() {
  if (saving.value || !dirty.value || !canSave() || !pdf.value) return;
  saving.value = true;
  try {
    const data = await pdf.value.saveDocument();
    let bin = "";
    for (let i = 0; i < data.length; i += 32768)
      bin += String.fromCharCode.apply(null, data.subarray(i, i + 32768));
    const res = await window.pywebview.api.write_pdf(props.scope, props.path, btoa(bin));
    if (res && res.error) { showToast(res.error); return; }
    pdf.value.annotationStorage.resetModified();
    dirty.value = false;
    emit("saved", data);
    showToast("Form saved");
  } catch (e) {
    showToast("PDF save failed: " + ((e && e.message) || e));
  } finally {
    saving.value = false;
  }
}

function onKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    save();
  }
}

// --- fit-width plumbing (re-measure on container resize) ---

async function recomputeFit() {
  await nextTick();
  if (!pdf.value) return;
  const page = await pdf.value.getPage(1);
  const vp = page.getViewport({ scale: 1 });
  basePageW.value = vp.width;
  basePageH.value = vp.height;
  const avail = Math.max((wrapRef.value?.clientWidth || 0) - 72, 320);
  fitScale.value = avail / basePageW.value;
}

// --- resize ---

let resizeObs = null;
let resizeTimer = null;
let lastFitW = 0;

// --- fallback ---

function enterFallback(why) {
  if (fallbackUrl.value) return;
  clearTimeout(stallTimer);
  console.warn("[pdf] falling back to native embed:", why);
  fallbackUrl.value = URL.createObjectURL(new Blob([props.bytes], { type: "application/pdf" }));
}

// --- document loading (extracted so it can run on mount AND on byte changes) ---

async function loadDocument() {
  // Tear down the previous document so its pages don't linger in memory.
  if (pdf.value) { pdf.value.destroy(); pdf.value = null; }
  clearTimeout(stallTimer);
  fallbackUrl.value = "";

  const sizeKB = (props.bytes && props.bytes.length || 0) / 1024;
  const stallMs = Math.max(15000, Math.min(sizeKB * 3, 45000));
  stallTimer = setTimeout(() => enterFallback("stalled"), stallMs);

  try {
    const doc = await pdfjs.getDocument({ data: props.bytes.slice() }).promise;
    clearTimeout(stallTimer);
    pageCount.value = doc.numPages;
    doc.annotationStorage.onSetModified = () => { dirty.value = true; };
    doc.annotationStorage.onResetModified = () => { dirty.value = false; };

    // Load field objects BEFORE setting pdf.value — PdfPage re-renders the
    // instant pdf.value changes, and the annotation layer needs fieldObjects
    // to populate input values for filled forms. Without this the inputs are
    // created but empty (the classic "form looks blank" bug).
    try { fieldObjects.value = await doc.getFieldObjects(); } catch { fieldObjects.value = null; }

    pdf.value = doc;  // triggers PdfPage re-render — fieldObjects is ready now

    const page = await doc.getPage(1);
    const vp = page.getViewport({ scale: 1 });
    basePageW.value = vp.width;
    basePageH.value = vp.height;
    const avail = Math.max((wrapRef.value?.clientWidth || 0) - 72, 320);
    fitScale.value = avail / basePageW.value;
  } catch (e) {
    enterFallback((e && e.message) || String(e));
  }
}

// --- lifecycle ---

onMounted(async () => {
  // Fit-width resize observer — set up once, lives for the component's lifetime.
  resizeObs = new ResizeObserver(entries => {
    const w = entries[entries.length - 1].contentRect.width;
    if (!basePageH.value || zoom.value !== 0) { lastFitW = w; return; }
    if (Math.abs(w - lastFitW) < 24) return;
    lastFitW = w;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(async () => {
      if (!basePageH.value || zoom.value !== 0) return;
      await recomputeFit();
    }, 180);
  });

  window.addEventListener("keydown", onKeydown);

  await loadDocument();

  // RecycleScroller needs extra time to mount its internal DOM;
  // a single nextTick isn't enough.
  await new Promise(r => setTimeout(r, 150));
  const sel = scrollerRef.value?.$el;
  if (sel) {
    resizeObs.observe(sel);
    lastFitW = sel.clientWidth;
  }
  if (props.targetPage > 1) {
    nextTick().then(() => scrollToPage(props.targetPage));
  }
});

onBeforeUnmount(() => {
  clearTimeout(stallTimer);
  clearTimeout(resizeTimer);
  window.removeEventListener("keydown", onKeydown);
  if (resizeObs) resizeObs.disconnect();
  if (pdf.value) pdf.value.destroy();
  if (fallbackUrl.value) URL.revokeObjectURL(fallbackUrl.value);
});

// --- hot-reload: when the agent fills the form on disk, refreshOpenDocs swaps
// the bytes prop — reload the document so the viewer reflects the new field
// values without losing zoom or scroll position. ---
watch(() => props.bytes, () => {
  if (!props.bytes || !props.bytes.length) return;
  loadDocument();
});

// --- external navigation (citation click) ---

watch(() => [props.targetPage, props.targetSeq], ([page]) => {
  if (!page || !pageCount.value || !basePageH.value) return;
  scrollToPage(page);
});
</script>

<template>
  <div ref="wrapRef" class="pv-wrap">
    <embed v-if="fallbackUrl" class="pv-native" :src="fallbackUrl" type="application/pdf" />
    <div v-show="!fallbackUrl && pageCount > 0" class="pv-bar">
      <span class="pb-pos">PAGE {{ pageNo }} / {{ pageCount }}</span>
      <button v-if="dirty && canSave()" class="pb-btn pb-save" :disabled="saving"
              title="Save filled form (Ctrl+S)" @click="save">
        {{ saving ? "SAVING…" : "SAVE" }}
      </button>
      <span class="pb-sp"></span>
      <button class="pb-btn" title="Zoom out" @click="setZoom(-1)">−</button>
      <span class="pb-zoom">{{ zoomLabel() }}</span>
      <button class="pb-btn" title="Zoom in" @click="setZoom(1)">+</button>
      <button class="pb-btn pb-fit" :class="{ on: zoom === 0 }" title="Fit width" @click="setZoom(0)">FIT</button>
    </div>
    <div v-show="!fallbackUrl && !basePageH" class="pv-loading">
      <div class="pv-spin"></div><span>Rendering…</span>
    </div>
    <RecycleScroller
      v-show="!fallbackUrl && basePageH"
      ref="scrollerRef"
      class="pv-scroll"
      :items="pageItems"
      :item-size="ITEM_HEIGHT"
      key-field="num"
      :buffer="2000"
      @scroll="onVirtualScroll"
    >
        <template #default="{ item }">
          <PdfPage
            :pdf="pdf"
            :page-num="item.num"
            :scale="currentScale()"
            :item-height="ITEM_HEIGHT"
            :page-width="pageWidth"
            :page-height="pageHeight"
            :field-objects="fieldObjects"
            :link-service="linkService"
          />
        </template>
    </RecycleScroller>
  </div>
</template>

<style scoped>
.pv-wrap {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  background: var(--bg-0);
}
.pv-bar {
  display: flex; align-items: center; gap: 8px; padding: 6px 14px; flex: none;
  border-bottom: 1px solid var(--line); background: var(--bg-1);
  font-family: var(--mono); font-size: 10px; letter-spacing: .08em; color: var(--text-3);
}
.pb-pos { color: var(--text-3); }
.pb-sp { flex: 1; }
.pb-btn {
  background: none; border: 1px solid var(--line); color: var(--text-3); cursor: pointer;
  font-family: var(--mono); font-size: 11px; line-height: 1; padding: 4px 9px; border-radius: 3px;
}
.pb-btn:hover { color: var(--text-1); border-color: var(--text-4); }
.pb-fit { font-size: 9px; letter-spacing: .1em; }
.pb-fit.on { color: var(--brand); border-color: var(--brand-dim, var(--brand)); }
.pb-save { color: var(--brand); border-color: var(--brand); font-size: 9px; letter-spacing: .1em; }
.pb-save:hover { color: var(--brand); }
.pb-save:disabled { opacity: .5; cursor: default; }
.pb-zoom { min-width: 42px; text-align: center; color: var(--text-2); }
.pv-scroll {
  flex: 1;
  /* RecycleScroller manages its own overflow-y; overflow-x clips the
     horizontal scrollbar that would otherwise appear for fit-width pages */
  overflow: hidden;
}
.pv-scroll :deep(.vue-recycle-scroller__item-view) {
  /* center page within each item slot */
  display: flex; justify-content: center;
}
.pv-loading {
  display: flex; align-items: center; justify-content: center; gap: 10px;
  padding: 60px 0; font: 400 11px var(--mono); color: var(--text-4); letter-spacing: .04em;
}
.pv-spin {
  width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0;
  border: 1.5px solid var(--border); border-top-color: var(--brand);
  animation: pv-rot 0.7s linear infinite;
}
@keyframes pv-rot { to { transform: rotate(360deg); } }
.pv-native { flex: 1; width: 100%; border: 0; }
</style>
