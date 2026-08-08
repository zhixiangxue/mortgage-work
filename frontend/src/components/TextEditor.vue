<script setup>
/* CodeMirror 6 pane for repo text files. IDE model: keystrokes only touch the
   in-memory copy (stageRepoFile); nothing hits disk until an explicit
   Ctrl/Cmd+S — the dirty dot in the breadcrumb tells the truth. */
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { EditorView, keymap, drawSelection, highlightActiveLine, highlightSpecialChars } from "@codemirror/view";
import { Compartment, EditorState } from "@codemirror/state";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { defaultHighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { markdown } from "@codemirror/lang-markdown";
import { yaml } from "@codemirror/lang-yaml";
import { oneDarkHighlightStyle } from "@codemirror/theme-one-dark";
import { saveRepoFile, stageRepoFile, store } from "../store.js";

const props = defineProps({ file: { type: Object, required: true } });
const host = ref(null);
let view = null;

// ── Font size zoom (Ctrl/Cmd + scroll) ──
// Persisted per-machine so the LO sets it once and it sticks across restarts.
const FONT_SIZE_KEY = "editor-font-size";
const DEFAULT_SIZE = 12.5;
const MIN_SIZE = 10;
const MAX_SIZE = 24;

function readFontSize() {
  try {
    const v = parseFloat(localStorage.getItem(FONT_SIZE_KEY));
    return Number.isFinite(v) ? Math.max(MIN_SIZE, Math.min(MAX_SIZE, v)) : DEFAULT_SIZE;
  } catch { return DEFAULT_SIZE; }
}

const fontSize = ref(readFontSize());

function applyFontSize() {
  if (view) view.dom.style.fontSize = fontSize.value + "px";
}

function onEditorWheel(e) {
  if (!e.ctrlKey && !e.metaKey) return;
  e.preventDefault();
  fontSize.value = Math.max(MIN_SIZE, Math.min(MAX_SIZE,
    fontSize.value + (e.deltaY < 0 ? 1 : -1)
  ));
  applyFontSize();
  try { localStorage.setItem(FONT_SIZE_KEY, String(fontSize.value)); } catch { /* quota */ }
}

// Captured at mount — the docs entry may already be gone when we unmount
const { scope, path } = props.file;

// ── Image paste (Ctrl/Cmd+V when clipboard holds an image) ──
// LO workflow: copy screenshot → paste into markdown doc → image lands in
// assets/ and a ![name](assets/name) link is inserted at the cursor.
async function handlePastedImage(file, view) {
  try {
    const b64 = await new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result).split(",", 2)[1] || "");
      r.onerror = () => reject(new Error("Could not read image"));
      r.readAsDataURL(file);
    });

    // Unique filename: pasted_20260808T143021Z.png
    const ts = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
    const ext = file.type.split("/")[1] || (file.name.split(".").pop() || "png");
    const name = `pasted_${ts}.${ext}`;

    if (!window.pywebview) {
      // Dev fallback: just insert the link without uploading
      const md = `![${name}](assets/${name})`;
      view.dispatch({
        changes: { from: view.state.selection.main.from, insert: md },
      });
      return;
    }

    const res = await window.pywebview.api.upload_files(scope, "assets", [{ name, b64 }]);
    if (res && res.error) {
      console.error("Image paste failed:", res.error);
      return;
    }

    const md = `![${name}](assets/${name})`;
    view.dispatch({
      changes: { from: view.state.selection.main.from, insert: md },
    });
  } catch (err) {
    console.error("Image paste error:", err);
  }
}

const imagePasteHandler = EditorView.domEventHandlers({
  paste(event, view) {
    const items = event.clipboardData?.items;
    if (!items || items.length === 0) return false;
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        event.preventDefault();
        const file = item.getAsFile();
        if (file) handlePastedImage(file, view);
        return true;
      }
    }
    return false; // let CodeMirror handle text paste normally
  },
});

function save() {
  if (view) saveRepoFile(scope, path, view.state.doc.toString());
  return true; // tell CodeMirror the key was handled (no browser Save dialog)
}

// Chrome-free theme: the pane should read as "the file", not as a dev tool.
// The surfaces are all var() so they follow data-theme by themselves; only the
// syntax palette and CodeMirror's own `dark` flag have to be swapped, which is
// what the compartment below is for.
const theme = EditorView.theme({
  "&": { backgroundColor: "transparent", height: "100%", fontSize: "12.5px" },
  ".cm-scroller": { fontFamily: "var(--mono)", lineHeight: "1.75", padding: "26px 34px 80px" },
  ".cm-content": { caretColor: "var(--brand)", color: "var(--text)" },
  "&.cm-focused": { outline: "none" },
  ".cm-activeLine": { backgroundColor: "var(--cm-active)" },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground":
    { backgroundColor: "var(--cm-select)" },
  ".cm-cursor": { borderLeftColor: "var(--brand)" },
});

const paletteComp = new Compartment();
const palette = name => [
  syntaxHighlighting(name === "dark" ? oneDarkHighlightStyle : defaultHighlightStyle),
  // Tells CodeMirror which way round its own defaults go (selection blending)
  EditorView.darkTheme.of(name === "dark"),
];

onMounted(() => {
  const lang = props.file.ext === "yaml" || props.file.ext === "yml" ? yaml() : markdown();
  view = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.file.content || "",
      extensions: [
        history(),
        drawSelection(),
        highlightSpecialChars(),
        highlightActiveLine(),
        EditorView.lineWrapping,
        paletteComp.of(palette(store.theme)),
        lang,
        theme,
        imagePasteHandler,
        keymap.of([
          { key: "Mod-s", run: save, preventDefault: true },
          ...defaultKeymap, ...historyKeymap, indentWithTab,
        ]),
        EditorView.updateListener.of(u => {
          if (!u.docChanged) return;
          // Memory only — the preview toggle and dirty flag stay honest,
          // but disk waits for Ctrl/Cmd+S.
          stageRepoFile(scope, path, u.state.doc.toString());
        }),
      ],
    }),
  });
  applyFontSize();
  view.dom.addEventListener("wheel", onEditorWheel, { passive: false });
});

// Theme flipped while a file was open: reconfigure in place rather than
// rebuilding the editor, so the cursor, scroll position and undo history stay.
watch(() => store.theme, name => {
  if (view) view.dispatch({ effects: paletteComp.reconfigure(palette(name)) });
});

// Disk changed under us (agent write, external edit → refreshOpenDocs swapped
// the store copy). CodeMirror owns its own buffer, so push the new text in.
// Only when clean: stageRepoFile sets dirty on every keystroke, and while the
// buffer is dirty refreshOpenDocs never touches content — so a change arriving
// here is always external, never an echo of the user's own typing.
watch(() => props.file.content, text => {
  if (!view || props.file.dirty || text === view.state.doc.toString()) return;
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text || "" } });
  // The dispatch above ran stageRepoFile and marked the doc dirty — undo that:
  // fresh disk content is the saved state, not an unsaved edit.
  props.file.content = text;
  props.file.dirty = false;
});

onBeforeUnmount(() => {
  // No implicit save: unsaved edits live on in the doc entry (mode switches),
  // and closeTab() already confirms before discarding a dirty one.
  if (view) {
    view.dom.removeEventListener("wheel", onEditorWheel);
    view.destroy();
  }
});
</script>

<template>
  <div ref="host" class="cm-host"></div>
</template>

<style scoped>
.cm-host { position: absolute; inset: 0; overflow: hidden; }
.cm-host :deep(.cm-editor) { height: 100%; }
</style>
