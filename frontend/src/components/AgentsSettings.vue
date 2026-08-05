<script setup>
/* Settings — Assistant Rules (AGENTS.md). The LO's personal instructions to
   the AI: focus, communication style, rules, lender preferences. Injected into
   the system prompt at the start of every new conversation. Stored at the repo
   root so it syncs across machines.

   Layout: a fixed header (title + save status + lede) over a CodeMirror 6
   editor that is the sole scroller — no nested scrollbars. Saves automatically
   (debounced), with an explicit Save button and Ctrl/Cmd+S to force a write.
   Reusing the same CodeMirror engine as TextEditor.vue so line numbers,
   scrolling, and resize all work perfectly out of the box. */
import { ref, computed, onMounted, onBeforeUnmount, watch } from "vue";
import { EditorView, keymap, drawSelection, highlightActiveLine, highlightSpecialChars, lineNumbers } from "@codemirror/view";
import { EditorState, Compartment } from "@codemirror/state";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { defaultHighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { markdown } from "@codemirror/lang-markdown";
import { oneDarkHighlightStyle } from "@codemirror/theme-one-dark";
import { store, loadAgentsMd, saveAgentsMd } from "../store.js";

const saveKey = /Mac/.test(navigator.platform) ? "⌘S" : "CTRL+S";

const BOOTSTRAP = `# Assistant Rules

<!-- This file personalizes your AI assistant across every chat. -->
<!-- Edit freely — it syncs with your repo and follows you across machines. -->

## Identity & Approach

<!-- You are a senior Loan Officer with an underwriter's analytical mindset. -->
<!-- Think like the person who will approve or deny this file, not just the one -->
<!-- who submits it. Anticipate underwriting objections before they arise.

Act as a senior Loan Officer paired with a meticulous underwriter. Your job is
not to push a loan through — it is to assess every file as if your own money
were on the line. When a borrower asks "can I qualify?", answer the way an
underwriter would: cite the specific rule, the math, and the documentation
needed to prove it.

## Communication Style

- Be thorough and precise. A one-line answer is usually a wrong answer in
  mortgage lending — explain the *why*, not just the *what*.
- Cite the numbers. Never state a DTI, LTV, or income figure without showing
  how it was calculated. If you don't have the source documents, say so and
  list what's missing.
- Structure complex answers: use headers, bullet points, and step-by-step
  breakdowns. A loan decision touches income, credit, assets, and collateral —
  organize the response the same way.
- When you identify a red flag or a potential denial reason, say it clearly and
  early. Don't bury problems; surface them so the LO can act.
- Use plain English with clients, but speak in full underwriting terminology
  (AUS findings, residual income, comp hits, overlay, etc.) with the LO.

## Analytical Rules

<!-- Hard rules the assistant must always follow when evaluating a file. -->

1. **Never quote income without source documents.** A pay stub, W-2, or 1099
   must back every dollar. For self-employed borrowers, require 2 years of
   tax returns plus YTD P&L. State the calculation method used (base, avg,
   or declining-income adjustment).
2. **Always calculate DTI two ways**: housing ratio (front-end) and total
   ratio (back-end). Flag anything over the program's limit and identify
   what's driving it.
3. **Verify LTV/CLTV against the appraisal, not the purchase price.** If no
   appraisal exists yet, state the assumption clearly.
4. **Read the credit report like an underwriter**: note the middle score,
   recent inquiries, disputed tradelines, and any derogatory events within
   the seasoning window. Flag comp hits and their impact.
5. **Check document recency.** Pay stubs must be within 30 days, asset
   statements within 60 days. Call out anything stale.
6. **When unsure about an overlay or guideline, say so.** Don't guess a
   lender's specific rule — ask which lender is in play, or recommend
   checking the matrix.

## Workflow

- Before recommending a loan product, confirm the borrower's complete picture:
  income, credit, assets, property type, occupancy, and transaction type.
- Use the available tools (income calculator, DTI calculator, LTV/CLTV,
  credit analyzer, doc checklist) whenever concrete numbers are involved —
  never do mortgage math in your head.
- Always end a file review with a clear verdict: **Approve / Approve with
  conditions / Deny**, followed by the specific conditions or reasons.

## Lender Preferences
<!-- Which lenders do you reach for first, and in what order? -->
<!-- e.g. itrust for non-QM, JMAC for FHA, NewWave for bank statement programs. -->
`;

const editorHost = ref(null);
let view = null;
let saveTimer = null;

const status = ref("idle");     // idle | loading | saving | saved | dirty
const dirty = ref(false);

const statusLabel = computed(() => {
  switch (status.value) {
    case "loading": return "Loading";
    case "saving": return "Saving";
    case "saved": return "Saved";
    case "dirty": return "Editing";
    default: return "";
  }
});

/* CodeMirror theme — chrome-free, surfaces all use var() so data-theme works.
   Line numbers (gutter) are dim so they stay out of the way; the caret and
   active line echo the app's IDE language. Mirrors TextEditor.vue's theme. */
const theme = EditorView.theme({
  "&": { backgroundColor: "transparent", height: "100%", fontSize: "12.5px" },
  ".cm-scroller": { fontFamily: "var(--mono)", lineHeight: "1.7", padding: "16px 28px 40px" },
  ".cm-content": { caretColor: "var(--brand)", color: "var(--text)" },
  "&.cm-focused": { outline: "none" },
  ".cm-gutters": {
    backgroundColor: "transparent", borderRight: "1px solid var(--border)",
    color: "var(--text-4)",
  },
  ".cm-activeLineGutter": { backgroundColor: "transparent", color: "var(--text-3)" },
  ".cm-activeLine": { backgroundColor: "var(--cm-active)" },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground":
    { backgroundColor: "var(--cm-select)" },
  ".cm-cursor": { borderLeftColor: "var(--brand)" },
});

const paletteComp = new Compartment();
const palette = name => [
  syntaxHighlighting(name === "dark" ? oneDarkHighlightStyle : defaultHighlightStyle),
  EditorView.darkTheme.of(name === "dark"),
];

function doSave() {
  status.value = "saving";
  const content = view ? view.state.doc.toString() : "";
  saveAgentsMd(content).then(res => {
    if (res && res.ok) {
      status.value = "saved";
      dirty.value = false;
      setTimeout(() => { if (status.value === "saved") status.value = "idle"; }, 2500);
    } else {
      status.value = "dirty";
    }
  });
}

function onDocChange() {
  dirty.value = true;
  status.value = "dirty";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(doSave, 1500);
}

function saveNow() {
  clearTimeout(saveTimer);
  doSave();
}

onMounted(() => {
  status.value = "loading";
  loadAgentsMd().then(res => {
    const initial = res && res.exists && res.content ? res.content : BOOTSTRAP;
    status.value = "idle";

    view = new EditorView({
      parent: editorHost.value,
      state: EditorState.create({
        doc: initial,
        extensions: [
          history(),
          drawSelection(),
          highlightSpecialChars(),
          highlightActiveLine(),
          EditorView.lineWrapping,
          lineNumbers(),
          paletteComp.of(palette(store.theme)),
          markdown(),
          theme,
          keymap.of([
            { key: "Mod-s", run: () => { saveNow(); return true; }, preventDefault: true },
            ...defaultKeymap, ...historyKeymap, indentWithTab,
          ]),
          EditorView.updateListener.of(u => { if (u.docChanged) onDocChange(); }),
        ],
      }),
    });
  });
});

// Theme flipped while open: reconfigure in place so cursor/scroll/undo survive
watch(() => store.theme, name => {
  if (view) view.dispatch({ effects: paletteComp.reconfigure(palette(name)) });
});

onBeforeUnmount(() => {
  clearTimeout(saveTimer);
  if (view) view.destroy();
});
</script>

<template>
  <div class="agents-pane">
    <div class="agents-inner">
      <!-- Fixed header: title, live save status, and a one-line lede that
           explains what this is and how saving works. No mystery box. -->
      <div class="agents-head">
        <div class="agents-title-row">
          <h1>Assistant Rules</h1>
          <span class="save-status" :class="status" v-if="statusLabel">
            <span class="ss-dot"></span>{{ statusLabel }}
          </span>
          <button class="btn-sm save-btn" :class="{ primary: dirty }"
                  :disabled="status === 'saving' || status === 'loading'"
                  @click="saveNow()">Save</button>
        </div>
        <p class="agents-lede">
          These rules shape every new chat — your focus, communication style,
          and lender preferences are sent to the assistant automatically.
          Changes save as you type; press <kbd>{{ saveKey }}</kbd> to save now.
        </p>
      </div>

      <!-- CodeMirror editor: fills the remaining height, sole scroller. The
           gutter (line numbers) is built in — no manual scroll syncing. The
           shell bg (--bg) is one shade deeper than the header (--bg-editor),
           making the editor read as a sunken input well. -->
      <div class="editor-shell">
        <div ref="editorHost" class="cm-host"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Flex-fill the settings content area; the editor becomes the sole scroller */
.agents-pane {
  height: 100%; display: flex; flex-direction: column;
  min-height: 0; background: var(--bg-editor);
}
/* Full width — an editor pane should fill its canvas, not float centered */
.agents-inner {
  flex: 1; min-height: 0; display: flex; flex-direction: column;
}

.agents-head { flex-shrink: 0; padding: 20px 32px 10px; }
.agents-title-row { display: flex; align-items: center; gap: 12px; }
.agents-title-row h1 {
  margin: 0;
  font: 700 15px var(--mono); letter-spacing: .3px; color: var(--text);
}

/* Save status — a colored dot + label. Amber while editing, pulsing while
   saving, brand-green once written, then it fades to idle. */
.save-status {
  display: inline-flex; align-items: center; gap: 6px;
  font: 500 9px var(--mono); letter-spacing: 1px; text-transform: uppercase;
  color: var(--text-4);
}
.save-status .ss-dot {
  width: 6px; height: 6px; border-radius: 50%; background: currentColor;
}
.save-status.dirty { color: var(--amber); }
.save-status.saving { color: var(--text-2); }
.save-status.saving .ss-dot { animation: ss-pulse 1.1s infinite; }
.save-status.saved { color: var(--brand); }
@keyframes ss-pulse { 50% { opacity: .3; } }

/* Save button sits at the right edge; primary (brand) only when there's
   something unsaved, otherwise a quiet outline. */
.save-btn { margin-left: auto; }
.save-btn:disabled { opacity: .35; cursor: default; }
.save-btn:disabled:hover { border-color: var(--border-soft); color: var(--text-2); }

/* One-line explainer — answers "what is this?" and "do I need to save?" */
.agents-lede {
  margin: 8px 0 0;
  font: 400 11.5px/1.6 var(--sans); color: var(--text-3);
}
.agents-lede kbd {
  font: 500 10px var(--mono); color: var(--text-2);
  border: 1px solid var(--border-soft); border-radius: 3px;
  padding: 1px 5px; background: var(--bg-hover);
}

/* Sunken "input well" — one shade deeper than the header (bg-editor), but
   still inside the app's warm-grey family so it doesn't break apart visually.
   Pure --bg (#000) was too stark and clashed with the surrounding surfaces. */
.editor-shell {
  flex: 1; min-height: 0;
  background: var(--bg-hover);
  border-top: 1px solid var(--border);
}
.cm-host { position: relative; height: 100%; overflow: hidden; }
.cm-host :deep(.cm-editor) { height: 100%; }
.cm-host :deep(.cm-scroller) { overflow: auto; }
</style>
