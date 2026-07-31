<script setup>
/* pdf.js viewer — same engine Firefox ships. Pages render onto canvases at
   devicePixelRatio so text is crisp, with a minimal dark toolbar: page
   position, zoom, fit-width.

   NO worker thread, on purpose. The worker loading chain (module worker →
   fake-worker dynamic import) proved fragile inside the old WKWebView that
   macOS ships, failing differently at each step. Instead the worker module
   is compiled INTO this (lazy) chunk through our own transpile pipeline and
   registered as the main-thread handler: zero runtime loading, nothing left
   to hang. Local files ≤ 40MB render fine on the main thread.

   And if pdf.js still fails or stalls, we fall back to the OS-native PDF
   plugin (<embed>) — less pretty, but a viewer that always opens beats a
   pretty error card.

   Fillable forms (AcroForm) stay fillable: fields render as real HTML
   inputs on an AnnotationLayer above the canvas, values live in pdf.js's
   annotationStorage, and SAVE (or Ctrl+S) writes the filled PDF back over
   the repo file through write_pdf. */
import { onBeforeUnmount, onMounted, ref } from "vue";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import { WorkerMessageHandler } from "pdfjs-dist/legacy/build/pdf.worker.mjs";
import { SimpleLinkService } from "pdfjs-dist/legacy/web/pdf_viewer.mjs";
import "pdfjs-dist/legacy/web/pdf_viewer.css"; // .annotationLayer widget styles
import { showToast } from "../store.js";

// pdf.js checks this global before ever touching workerSrc — explicit
// assignment so bundler side-effect pruning can't break it
globalThis.pdfjsWorker = { WorkerMessageHandler };

const props = defineProps({
  bytes: { type: Uint8Array, required: true },
  // Where the bytes came from — needed to save a filled form back. Absent
  // in demo mode, which simply means the SAVE button never appears.
  scope: { type: String, default: "" },
  path: { type: String, default: "" },
});
const emit = defineEmits(["saved"]);
const scroller = ref(null);
const pagesEl = ref(null);
const pageNo = ref(1);
const pageCount = ref(0);
const zoom = ref(0); // 0 = fit width; otherwise an absolute scale factor
const fallbackUrl = ref(""); // non-empty ⇒ native <embed> takes over
const dirty = ref(false); // form fields touched since the last save
const saving = ref(false);

let pdf = null;
let fitScale = 1;
let renderSeq = 0; // bumped per re-render so stale async passes bail out
let settled = false;
let stallTimer = null;
let fieldObjects = null; // AcroForm field map, fetched once after decode
const linkService = new SimpleLinkService(); // inert but AnnotationLayer wants one

function currentScale() { return zoom.value || fitScale; }
const zoomLabel = () => Math.round((currentScale() / fitScale) * 100) + "%";

async function renderAll() {
  const seq = ++renderSeq;
  const holder = pagesEl.value;
  holder.innerHTML = "";
  const dpr = window.devicePixelRatio || 1;
  for (let i = 1; i <= pdf.numPages; i++) {
    if (seq !== renderSeq) return;
    const page = await pdf.getPage(i);
    const vp = page.getViewport({ scale: currentScale() });
    // Wrapper hosts the canvas plus a transparent text layer on top — the
    // canvas is just pixels; selectable text is what the text layer is for
    const wrap = document.createElement("div");
    wrap.className = "pv-page";
    wrap.style.width = vp.width + "px";
    wrap.style.height = vp.height + "px";
    // pdf.js text layer positions its spans via this CSS variable
    wrap.style.setProperty("--scale-factor", vp.scale);
    const canvas = document.createElement("canvas");
    canvas.width = Math.floor(vp.width * dpr);
    canvas.height = Math.floor(vp.height * dpr);
    canvas.style.width = vp.width + "px";
    canvas.style.height = vp.height + "px";
    wrap.appendChild(canvas);
    holder.appendChild(wrap);
    await page.render({
      canvasContext: canvas.getContext("2d"),
      viewport: vp,
      transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : null,
      // Form fields become HTML inputs on the annotation layer below — keep
      // their appearance streams off the canvas or every field paints twice
      annotationMode: pdfjs.AnnotationMode.ENABLE_FORMS,
    }).promise;
    if (seq !== renderSeq) return;
    // Text layer is a bonus, not a requirement — scanned PDFs simply have no
    // text content, and a layer failure must never take the page image down
    try {
      const tl = document.createElement("div");
      tl.className = "textLayer";
      wrap.appendChild(tl);
      await new pdfjs.TextLayer({
        textContentSource: page.streamTextContent(),
        container: tl,
        viewport: vp,
      }).render();
    } catch { /* image-only page — nothing to select */ }
    if (seq !== renderSeq) return;
    // Annotation layer: real <input>/<select> widgets for AcroForm fields,
    // wired straight into annotationStorage. Same bonus rule as text.
    try {
      const annotations = await page.getAnnotations();
      if (annotations.length) {
        const al = document.createElement("div");
        al.className = "annotationLayer";
        wrap.appendChild(al);
        const layer = new pdfjs.AnnotationLayer({
          div: al,
          accessibilityManager: null,
          annotationCanvasMap: null,
          annotationEditorUIManager: null,
          page,
          viewport: vp.clone({ dontFlip: true }), // layer wants CSS-space y-axis
          structTreeLayer: null,
        });
        await layer.render({
          annotations,
          imageResourcesPath: "",
          renderForms: true,
          linkService,
          downloadManager: null,
          annotationStorage: pdf.annotationStorage,
          enableScripting: false,
          hasJSActions: false,
          fieldObjects,
        });
      }
    } catch (e) { console.warn("[pdf] annotation layer failed:", e); }
  }
}

const canSave = () => !!(props.scope && props.path);

async function save() {
  if (saving.value || !dirty.value || !canSave() || !pdf) return;
  saving.value = true;
  try {
    // saveDocument() bakes annotationStorage values into a fresh PDF
    const data = await pdf.saveDocument();
    // 32K chunks: one big String.fromCharCode blows the argument limit
    let bin = "";
    for (let i = 0; i < data.length; i += 32768)
      bin += String.fromCharCode.apply(null, data.subarray(i, i + 32768));
    const res = await window.pywebview.api.write_pdf(props.scope, props.path, btoa(bin));
    if (res && res.error) { showToast(res.error); return; }
    pdf.annotationStorage.resetModified();
    dirty.value = false;
    emit("saved", data); // store keeps the filled bytes for the next remount
    showToast("Form saved");
  } catch (e) {
    showToast("PDF save failed: " + ((e && e.message) || e));
  } finally {
    saving.value = false;
  }
}

function onKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault(); // swallow even when clean — browser Save dialog never helps here
    save();
  }
}

function computeFit() {
  // Two rAFs: panels/flex layout are often still settling the moment we
  // mount — measuring too early is how pages come out tiny
  return new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))
    .then(() => pdf.getPage(1))
    .then(page => {
      const w = page.getViewport({ scale: 1 }).width;
      // 72 = side gutters; floor keeps a degenerate measurement readable
      const avail = Math.max((scroller.value?.clientWidth || 0) - 72, 320);
      fitScale = avail / w;
    });
}

function setZoom(dir) {
  if (dir === 0) zoom.value = 0;
  else {
    const next = currentScale() * (dir > 0 ? 1.2 : 1 / 1.2);
    zoom.value = Math.min(fitScale * 4, Math.max(fitScale * 0.35, next));
  }
  renderAll();
}

function onScroll() {
  // Page indicator follows the page crossing the viewport's upper third
  const kids = pagesEl.value ? pagesEl.value.children : [];
  const mark = scroller.value.scrollTop + scroller.value.clientHeight / 3;
  for (let i = 0; i < kids.length; i++) {
    if (kids[i].offsetTop + kids[i].offsetHeight >= mark) { pageNo.value = i + 1; return; }
  }
}

// Last resort: hand the bytes to the OS-native PDF plugin. Ugly chrome,
// but it has rendered everything we ever threw at it.
function enterFallback(why) {
  if (fallbackUrl.value) return;
  settled = true;
  clearTimeout(stallTimer);
  console.warn("[pdf] falling back to native embed:", why);
  fallbackUrl.value = URL.createObjectURL(new Blob([props.bytes], { type: "application/pdf" }));
}

let resizeObs = null;
let lastFitW = 0;
onMounted(async () => {
  // pdf.js runs on our main thread now — if it hasn't produced a page count
  // in 8s something is wedged; stop waiting and show the native viewer
  stallTimer = setTimeout(() => { if (!settled) enterFallback("stalled"); }, 8000);
  // Register BEFORE the async decode: fit-width must track every container
  // width change (panel open/close, sidebar drag, late layout settling),
  // including ones that happen while pages are still rendering.
  resizeObs = new ResizeObserver(entries => {
    const w = entries[entries.length - 1].contentRect.width;
    if (Math.abs(w - lastFitW) < 2) return; // ignore sub-pixel jitter
    lastFitW = w;
    if (!pdf || zoom.value !== 0) return;
    computeFit().then(renderAll);
  });
  resizeObs.observe(scroller.value);
  try {
    // .slice(): pdf.js detaches the buffer it consumes, but the store keeps
    // the original so tab switches can remount us
    pdf = await pdfjs.getDocument({ data: props.bytes.slice() }).promise;
    settled = true;
    clearTimeout(stallTimer);
    pageCount.value = pdf.numPages;
    // Form plumbing before first render: the annotation layer needs the
    // field map, and dirty tracking must catch the very first keystroke
    try { fieldObjects = await pdf.getFieldObjects(); } catch { fieldObjects = null; }
    pdf.annotationStorage.onSetModified = () => { dirty.value = true; };
    pdf.annotationStorage.onResetModified = () => { dirty.value = false; };
    window.addEventListener("keydown", onKeydown);
    lastFitW = scroller.value ? scroller.value.clientWidth : 0;
    await computeFit();
    await renderAll();
  } catch (e) {
    enterFallback((e && e.message) || String(e));
  }
});

onBeforeUnmount(() => {
  renderSeq++; // cancel in-flight page loop
  clearTimeout(stallTimer);
  window.removeEventListener("keydown", onKeydown);
  if (resizeObs) resizeObs.disconnect();
  if (pdf) pdf.destroy();
  if (fallbackUrl.value) URL.revokeObjectURL(fallbackUrl.value);
});
</script>

<template>
  <div class="pv-wrap">
    <!-- Native fallback: the OS plugin brings its own UI -->
    <embed v-if="fallbackUrl" class="pv-native" :src="fallbackUrl" type="application/pdf" />
    <template v-else>
      <div class="pv-bar" v-if="pageCount > 0">
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
      <div ref="scroller" class="pv-scroll" @scroll="onScroll">
        <div v-if="pageCount === 0" class="pv-msg">Rendering…</div>
        <div ref="pagesEl" class="pv-pages"></div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* pv- prefix on purpose: global.css owns .pdf-wrap/.pdf-page for the demo's
   fake v-html viewer, and those globals leak through scoped styles — the
   centering + max-width there is exactly what shrank real pages to a strip. */
.pv-wrap { position: absolute; inset: 0; display: flex; flex-direction: column; background: var(--bg-0); }
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
.pv-scroll { flex: 1; overflow: auto; }
.pv-pages { display: flex; flex-direction: column; align-items: center; gap: 18px; padding: 24px 36px 60px; }
.pv-pages :deep(.pv-page) {
  /* Paper stays paper in both themes; only the shadow and the edge follow it */
  position: relative; background: #fff; border-radius: 2px;
  box-shadow: 0 2px 18px var(--shadow), 0 0 0 1px var(--border);
}
.pv-pages :deep(.pv-page canvas) { display: block; }
/* pdf.js text layer: invisible glyphs positioned over the canvas so native
   selection works. Minimal port of pdf.js's own text_layer_builder.css. */
.pv-pages :deep(.textLayer) {
  position: absolute; inset: 0; overflow: hidden;
  line-height: 1; transform-origin: 0 0; forced-color-adjust: none;
}
.pv-pages :deep(.textLayer span),
.pv-pages :deep(.textLayer br) {
  color: transparent; position: absolute; white-space: pre;
  cursor: text; transform-origin: 0 0;
}
/* Translucent highlight — the canvas glyphs underneath must stay readable */
.pv-pages :deep(.textLayer span::selection) {
  background: color-mix(in srgb, var(--brand) 30%, transparent);
  color: transparent;
}
.pv-msg {
  padding: 60px 0; text-align: center;
  font-family: var(--mono); font-size: 11px; letter-spacing: .08em; color: var(--text-4);
}
.pv-native { flex: 1; width: 100%; border: 0; }
</style>
