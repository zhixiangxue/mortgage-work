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

// Captured at mount — the docs entry may already be gone when we unmount
const { scope, path } = props.file;

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
  if (view) view.destroy();
});
</script>

<template>
  <div ref="host" class="cm-host"></div>
</template>

<style scoped>
.cm-host { position: absolute; inset: 0; overflow: hidden; }
.cm-host :deep(.cm-editor) { height: 100%; }
</style>
