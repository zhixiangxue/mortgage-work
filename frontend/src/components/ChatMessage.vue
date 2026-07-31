<script setup>
/* One chat turn. Assistant turns render markdown (markdown-it, html:false so
   raw HTML from the model stays escaped); user turns render custom.display —
   the typed words plus pill components for files/folders/quotes, the same
   shapes the composer showed — never the serialized prompt the model got.
   Message shape = chak dump ({role, content, attachments?, custom?}) plus
   the local extras chatws.js adds (_streaming, tools). */
import { computed } from "vue";
import MarkdownIt from "markdown-it";
import { showToast } from "../store.js";
import { deleteTurn, retrySend } from "../chatws.js";
import { SVG_FILE, SVG_FOLDER, SVG_QUOTE } from "../utils.js";

const props = defineProps({ msg: { type: Object, required: true } });

const md = new MarkdownIt({ html: false, linkify: true, breaks: true });

const isAI = computed(() => props.msg.role === "assistant");
const html = computed(() => md.render(props.msg.content || ""));
const cancelled = computed(() => !!(props.msg.custom && props.msg.custom.cancelled));

/* The composer's structured form, stamped server-side onto the HumanMessage
   (and mirrored by the optimistic send). Old transcripts predate it — they
   fall back to raw content + whatever attachment names survive. */
const display = computed(() => (props.msg.custom && props.msg.custom.display) || null);
const utext = computed(() => display.value ? display.value.text : props.msg.content);

const filePills = computed(() => {
  if (display.value)
    return (display.value.pills || []).map(p => ({
      name: p.name || String(p.path || "").split("/").pop() || p.scope,
      dir: !!p.dir || !p.path,
      title: `${p.scope}/${p.path || ""}`,
    }));
  // Legacy: optimistic pills from older sessions / chak attachments
  if (props.msg.pills && props.msg.pills.length)
    return props.msg.pills.map(p => ({ name: String(p.path || "").split("/").pop() || p.scope, dir: !p.path, title: `${p.scope}/${p.path}` }));
  return (props.msg.attachments || []).map(a => {
    const src = String(a.source || "");
    return { name: src.split(/[\\/]/).pop(), dir: false, title: src };
  });
});

const quotePills = computed(() => !display.value ? [] :
  (display.value.quotes || []).map(q => ({
    label: q.text.length > 80 ? q.text.slice(0, 80).trimEnd() + "…" : q.text,
    src: q.path ? q.path.split("/").pop() : "",
    title: (q.path ? `${q.scope}/${q.path}\n` : "") + `\u201C${q.text}\u201D`,
  })));

const SVG_COPY = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
const SVG_TRASH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>`;
const SVG_FAIL = `<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"/><rect x="11" y="6" width="2" height="8" rx="1" fill="var(--bg, #fff)"/><circle cx="12" cy="17" r="1.3" fill="var(--bg, #fff)"/></svg>`;

function copy() {
  navigator.clipboard && navigator.clipboard.writeText(props.msg.content || "");
  showToast("Copied to clipboard");
}

/* Deleting either side removes the whole turn — a question without its
   answer (or the reverse) is meaningless in the transcript and would strand
   tool_calls halfway. The server cascades via the shared turn_id. */
function del() {
  deleteTurn(props.msg.turn_id);
}
</script>

<template>
  <div class="msg" :class="isAI ? 'ai' : 'user'">
    <div class="brow">
      <!-- WeChat-style failed-send mark: the send never reached the model;
           clicking resends the same text + pills -->
      <button v-if="msg._failed" class="fail" data-tip="Failed — click to resend"
              @click="retrySend(msg)" v-html="SVG_FAIL"></button>
      <div class="bubble">
      <!-- Tool trace — nothing emits these in V1 (tools=[]), block is ready -->
      <div v-if="msg.tools && msg.tools.length" class="trace">
        <div class="t-head"><span>AGENT · {{ msg.tools.length }} TOOL CALL{{ msg.tools.length > 1 ? "S" : "" }}</span></div>
        <pre><template v-for="t in msg.tools" :key="t.call_id"><span class="op">{{ t.tool }}</span> <span :class="t.status === 'error' ? 'errx' : 'okx'">{{ t.status === "run" ? "…" : t.status === "ok" ? "✓" : "✗ " + (t.error || "") }}</span>
</template></pre>
      </div>
      <div v-if="isAI" class="md" v-html="html"></div>
      <span v-else-if="utext" class="utext">{{ utext }}</span>
      <span v-if="msg._streaming" class="cursor">▊</span>
      <!-- Quoted passages — same pill the composer showed, provenance on hover -->
      <div v-if="quotePills.length" class="chips">
        <span v-for="(q, i) in quotePills" :key="'q' + i" class="pill quote" :title="q.title">
          <span v-html="SVG_QUOTE"></span><span class="q">{{ q.label }}</span>
          <span v-if="q.src" class="src">{{ q.src }}</span>
        </span>
      </div>
      <!-- Attached files/folders — icon pills, not serialized paths -->
      <div v-if="filePills.length" class="chips">
        <span v-for="(c, i) in filePills" :key="i" class="pill" :title="c.title">
          <span v-html="c.dir ? SVG_FOLDER : SVG_FILE"></span>{{ c.name }}
        </span>
      </div>
      <div v-if="cancelled" class="stopped">■ stopped</div>
      </div>
    </div>
    <div class="msg-acts">
      <button v-if="isAI && !msg._streaming" data-tip="Copy" @click="copy" v-html="SVG_COPY"></button>
      <button v-if="!msg._streaming && msg.turn_id" class="del" data-tip="Delete turn"
              @click="del" v-html="SVG_TRASH"></button>
    </div>
  </div>
</template>

<style scoped>
.brow { display: flex; align-items: center; gap: 7px; max-width: 100%; }
.fail {
  background: none; border: none; padding: 0; cursor: pointer;
  color: var(--red); display: flex; flex: none;
}
/* :deep() — the svg arrives via v-html, so it never gets the scope id */
.fail :deep(svg) { width: 15px; height: 15px; }
.utext { white-space: pre-wrap; word-break: break-word; }
.cursor { color: var(--brand); }
.chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
/* Echoed pills reuse the global .pill/.pill.quote look from the composer —
   the bubble shows the same components the user just dragged in. The svg
   arrives via v-html inside a wrapper span; size it like composer pills. */
.pill { margin: 0; max-width: 100%; }
.pill > span:first-child { display: inline-flex; flex-shrink: 0; }
.pill :deep(svg) { width: 11px; height: 11px; }
.pill.quote .q { overflow: hidden; text-overflow: ellipsis; }
.stopped { font: 400 10px var(--mono); color: var(--text-4); margin-top: 4px; }
/* Markdown body — the model writes paragraphs/lists/code, keep them compact
   inside a 12.5px bubble. :deep() because v-html output has no scope ids. */
.md :deep(p) { margin: 0 0 8px; }
.md :deep(p:last-child), .md :deep(ul:last-child), .md :deep(ol:last-child),
.md :deep(pre:last-child) { margin-bottom: 0; }
.md :deep(ul), .md :deep(ol) { margin: 0 0 8px; padding-left: 18px; }
.md :deep(li) { margin: 2px 0; }
.md :deep(code) { background: var(--bg-raise); padding: 1px 5px; font: 11px var(--mono); color: var(--brand); }
.md :deep(pre) {
  background: var(--bg-raise); padding: 8px 10px; margin: 0 0 8px;
  overflow-x: auto; font: 11px var(--mono);
}
.md :deep(pre code) { background: none; padding: 0; color: var(--text-2); }
.md :deep(h1), .md :deep(h2), .md :deep(h3), .md :deep(h4) {
  font-size: 12.5px; margin: 10px 0 6px; color: var(--text);
}
.md :deep(blockquote) {
  margin: 0 0 8px; padding: 2px 10px;
  border-left: 2px solid var(--border-soft); color: var(--text-3);
}
.md :deep(a) { color: var(--brand); }
.md :deep(table) { border-collapse: collapse; margin: 0 0 8px; font-size: 11.5px; }
.md :deep(th), .md :deep(td) { border: 1px solid var(--border); padding: 3px 8px; }
.md :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 8px 0; }
/* Tool trace reuses the global .trace look from the mock era */
.errx { color: var(--red); }
</style>
