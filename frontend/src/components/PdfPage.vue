<script setup>
import { ref, watch, onBeforeUnmount } from "vue";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";

const props = defineProps({
  pdf: { type: Object, required: true },
  pageNum: { type: Number, required: true },
  scale: { type: Number, required: true },
  /** Outer wrapper height fed back to the virtual scroller as fixedItemHeight. */
  itemHeight: { type: Number, required: true },
  pageWidth: { type: Number, default: 0 },
  pageHeight: { type: Number, default: 0 },
  fieldObjects: { type: Object, default: null },
  linkService: { type: Object, default: null },
});

const canvasRef = ref(null);
const textLayerRef = ref(null);
const annotationLayerRef = ref(null);
const loading = ref(true);
const errorMsg = ref("");

let renderSeq = 0;
let currentPage = null;

function clearDom() {
  if (canvasRef.value) {
    const c = canvasRef.value;
    const ctx = c.getContext("2d");
    ctx && ctx.clearRect(0, 0, c.width, c.height);
    c.width = 0;
    c.height = 0;
    c.style.width = "0px";
    c.style.height = "0px";
  }
  if (textLayerRef.value) textLayerRef.value.innerHTML = "";
  if (annotationLayerRef.value) annotationLayerRef.value.innerHTML = "";
}

async function render() {
  // Abort any in-flight pass for a previous page
  renderSeq++;
  const seq = renderSeq;

  clearDom();
  loading.value = true;
  errorMsg.value = "";

  const canvas = canvasRef.value;
  if (!canvas || !props.pdf || props.pageNum < 1) return;

  try {
    const page = await props.pdf.getPage(props.pageNum);
    if (seq !== renderSeq) return;
    currentPage = page;

    const vp = page.getViewport({ scale: props.scale });
    const dpr = window.devicePixelRatio || 1;

    canvas.width = Math.floor(vp.width * dpr);
    canvas.height = Math.floor(vp.height * dpr);
    canvas.style.width = vp.width + "px";
    canvas.style.height = vp.height + "px";

    await page.render({
      canvasContext: canvas.getContext("2d"),
      viewport: vp,
      transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : null,
      annotationMode: pdfjs.AnnotationMode.ENABLE_FORMS,
    }).promise;
    if (seq !== renderSeq) return;

    // Text layer — best-effort; scanned PDFs have no text content
    try {
      const tl = textLayerRef.value;
      if (tl) {
        tl.style.setProperty("--scale-factor", String(vp.scale));
        await new pdfjs.TextLayer({
          textContentSource: page.streamTextContent(),
          container: tl,
          viewport: vp,
        }).render();
      }
    } catch { /* image-only page */ }
    if (seq !== renderSeq) return;

    // Annotation layer — AcroForm fields as native HTML inputs
    try {
      const al = annotationLayerRef.value;
      if (al) {
        const annotations = await page.getAnnotations();
        if (annotations.length) {
          await new pdfjs.AnnotationLayer({
            div: al,
            accessibilityManager: null,
            annotationCanvasMap: null,
            annotationEditorUIManager: null,
            page,
            viewport: vp.clone({ dontFlip: true }),
            structTreeLayer: null,
          }).render({
            annotations,
            imageResourcesPath: "",
            renderForms: true,
            linkService: props.linkService,
            downloadManager: null,
            annotationStorage: props.pdf.annotationStorage,
            enableScripting: false,
            hasJSActions: false,
            fieldObjects: props.fieldObjects,
          });
        }
      }
    } catch (e) { console.warn("[pdf] annotation layer failed:", e); }

    if (seq === renderSeq) loading.value = false;
  } catch (e) {
    if (seq === renderSeq) {
      errorMsg.value = (e && e.message) || String(e);
      loading.value = false;
    }
  }
}

watch(() => [props.pageNum, props.scale], render, { immediate: true });

onBeforeUnmount(() => {
  renderSeq++;
  if (currentPage) { currentPage.cleanup && currentPage.cleanup(); currentPage = null; }
});
</script>

<template>
  <div
    class="pp-item"
    :style="{ height: itemHeight + 'px', paddingBottom: (itemHeight - pageHeight) + 'px' }"
  >
    <div class="pp-page" :style="{ width: pageWidth + 'px', height: pageHeight + 'px' }">
      <div v-if="loading" class="pp-msg">Loading page {{ pageNum }}…</div>
      <div v-if="errorMsg" class="pp-msg pp-err">Error: {{ errorMsg }}</div>
      <canvas ref="canvasRef" class="pp-canvas" />
      <div ref="textLayerRef" class="textLayer" />
      <div ref="annotationLayerRef" class="annotationLayer" />
    </div>
  </div>
</template>

<style scoped>
.pp-item {
  box-sizing: border-box;
  display: flex; align-items: flex-start; justify-content: center;
}
.pp-page {
  position: relative;
  background: #fff;
  border-radius: 2px;
  box-shadow: 0 2px 18px var(--shadow), 0 0 0 1px var(--border);
  overflow: hidden;
}
.pp-canvas { display: block; }
.pp-msg {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 11px; color: var(--text-4); z-index: 1;
}
.pp-err { color: #c62828; }

/* pdf.js text layer: invisible glyphs over the canvas for native selection */
.textLayer {
  position: absolute; inset: 0; overflow: hidden;
  line-height: 1; transform-origin: 0 0; forced-color-adjust: none;
}
.textLayer :deep(span),
.textLayer :deep(br) {
  color: transparent; position: absolute; white-space: pre;
  cursor: text; transform-origin: 0 0;
}
.textLayer :deep(span::selection) {
  background: color-mix(in srgb, var(--brand) 30%, transparent);
  color: transparent;
}

/* annotationLayer — form fields */
.annotationLayer :deep(input),
.annotationLayer :deep(select) {
  font-family: inherit; font-size: inherit;
}
</style>
