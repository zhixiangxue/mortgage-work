<script setup>
/* CodeMirror 6 pane for repo text files. IDE model: keystrokes only touch the
   in-memory copy (stageRepoFile); nothing hits disk until an explicit
   Ctrl/Cmd+S — the dirty dot in the breadcrumb tells the truth. */
import { onBeforeUnmount, onMounted, ref } from "vue";
import { EditorView, keymap, drawSelection, highlightActiveLine, highlightSpecialChars } from "@codemirror/view";
import { EditorState } from "@codemirror/state";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { syntaxHighlighting } from "@codemirror/language";
import { markdown } from "@codemirror/lang-markdown";
import { yaml } from "@codemirror/lang-yaml";
import { oneDarkHighlightStyle } from "@codemirror/theme-one-dark";
import { saveRepoFile, stageRepoFile } from "../store.js";

const props = defineProps({ file: { type: Object, required: true } });
const host = ref(null);
let view = null;

// Captured at mount — the docs entry may already be gone when we unmount
const { scope, path } = props.file;

function save() {
  if (view) saveRepoFile(scope, path, view.state.doc.toString());
  return true; // tell CodeMirror the key was handled (no browser Save dialog)
}

// Chrome-free theme: the pane should read as "the file", not as a dev tool
const theme = EditorView.theme({
  "&": { backgroundColor: "transparent", height: "100%", fontSize: "12.5px" },
  ".cm-scroller": { fontFamily: "var(--mono)", lineHeight: "1.75", padding: "26px 34px 80px" },
  ".cm-content": { caretColor: "var(--brand)", color: "var(--text-1)" },
  "&.cm-focused": { outline: "none" },
  ".cm-activeLine": { backgroundColor: "rgba(255,255,255,.025)" },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground":
    { backgroundColor: "rgba(212,180,90,.16)" },
  ".cm-cursor": { borderLeftColor: "var(--brand)" },
}, { dark: true });

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
        syntaxHighlighting(oneDarkHighlightStyle),
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
