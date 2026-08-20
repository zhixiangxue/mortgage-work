<script setup>
/* One chat turn. Assistant turns render markdown (markdown-it, html:false so
   raw HTML from the model stays escaped); user turns render custom.display —
   the typed words plus pill components for files/folders/quotes, the same
   shapes the composer showed — never the serialized prompt the model got.
   Message shape = chak dump ({role, content, attachments?, custom?}) plus
   the local extras chatws.js adds (_streaming, tools). */
import { computed, reactive, watch } from "vue";
import MarkdownIt from "markdown-it";
import { openCitation, showToast } from "../store.js";
import { deleteTurn, retrySend, recallLastUserMessage, branchConv } from "../chatws.js";
import { SVG_FILE, SVG_FOLDER, SVG_QUOTE } from "../utils.js";

const props = defineProps({
  msg: { type: Object, required: true },
  isLastUser: { type: Boolean, default: false },
});

const emit = defineEmits(["reedit"]);

const citationNames = reactive({});
const pendingCitationNames = new Set();

function citationFileName(docId) {
  return citationNames[docId] || "PDF";
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
}

function scanCitations(content) {
  const text = String(content || "");
  const re = /mai:\/\/([^/\s)]+)\/(\d+)/g;
  let m;
  while ((m = re.exec(text))) {
    const docId = m[1];
    if (!docId || citationNames[docId] || pendingCitationNames.has(docId) || !window.pywebview) continue;
    pendingCitationNames.add(docId);
    window.pywebview.api.resolve_citation(docId).then(res => {
      if (res && !res.error && res.path) citationNames[docId] = String(res.path).split("/").pop();
    }).finally(() => pendingCitationNames.delete(docId));
  }
}

const md = new MarkdownIt({ html: false, linkify: true, breaks: true });
const defaultLinkOpen = md.renderer.rules.link_open || ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options));
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const href = tokens[idx].attrGet("href") || "";
  const m = href.match(/^mai:\/\/([^/]+)\/(\d+)$/);
  if (!m) return defaultLinkOpen(tokens, idx, options, env, self);
  const [, docId, page] = m;
  tokens[idx].attrJoin("class", "cite-badge");
  tokens[idx].attrSet("title", `Open ${citationFileName(docId)} page ${page}`);
  return defaultLinkOpen(tokens, idx, options, env, self)
    + `<span class="cite-file">${escapeHtml(citationFileName(docId))}</span>`
    + `<span class="cite-page">P.${escapeHtml(page)}</span>`;
};

const isAI = computed(() => props.msg.role === "assistant");
const html = computed(() => md.render(props.msg.content || ""));
const orderedParts = computed(() => Array.isArray(props.msg.parts) ? props.msg.parts.filter(p => p && (p.type === "text" || p.type === "tool")) : []);
function partHtml(part) { return md.render(part.content || ""); }
watch(() => props.msg.content, scanCitations, { immediate: true });
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
const SVG_BRANCH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>`;
const SVG_TRASH = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>`;
const SVG_FAIL = `<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"/><rect x="11" y="6" width="2" height="8" rx="1" fill="var(--bg, #fff)"/><circle cx="12" cy="17" r="1.3" fill="var(--bg, #fff)"/></svg>`;
const SVG_RECALL = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.5 17A9 9 0 1 0 2 11"/></svg>`;
const SVG_CHEV = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 6 15 12 9 18"/></svg>`;

/* Expandable tool steps: click a step row to inspect what the call sent and
   what came back. Arguments were parsed at call time; the result rides on the
   part (chatws.js attaches it from tool_end events / history tool messages). */
function toggleTool(part) { part._open = !part._open; }

/* Arguments render as labeled rows, not raw JSON — the reader is a loan
   officer, not a developer. Common keys get business names; the rest are
   humanized (start_page → "start page"). */
const ARG_LABELS = {
  path: "File", src: "From", dst: "To", source: "Document",
  question: "Question", query: "Query", request: "Request",
  pattern: "Pattern", section: "Section", doc_ids: "Documents",
  old_text: "Old text", new_text: "New text", content: "Content",
  offset: "Start line", limit: "Lines", max_results: "Max results",
  start_page: "Start page", end_page: "End page", page: "Page",
  format: "Format", max_chars: "Max chars", commit: "Commit",
  since: "Since", until: "Until", recursive: "Recursive",
};
function argLabel(key) { return ARG_LABELS[key] || String(key).replace(/_/g, " "); }
const ARG_VAL_CAP = 4000;
function argValue(v) {
  if (v == null) return "—";
  let s;
  if (Array.isArray(v)) s = v.join(", ");
  else if (typeof v === "object") { try { s = JSON.stringify(v); } catch { s = String(v); } }
  else s = String(v);
  return s.length > ARG_VAL_CAP ? s.slice(0, ARG_VAL_CAP) + "\n… [truncated]" : s;
}
/* Paths keep the mono face so they scan as paths; prose reads as prose. */
function isPathLike(v) {
  return typeof v === "string" && !/\s/.test(v) && /[/\\]/.test(v);
}
const RESULT_CAP = 16000;
function resultText(part) {
  const s = String(part.result ?? "");
  return s.length > RESULT_CAP ? s.slice(0, RESULT_CAP) + "\n… [truncated]" : s;
}

function copy() {
  navigator.clipboard && navigator.clipboard.writeText(props.msg.content || "");
  showToast("Copied to clipboard");
}

function onMarkdownClick(e) {
  const a = e.target && e.target.closest ? e.target.closest("a") : null;
  if (!a) return;
  const href = a.getAttribute("href") || "";
  if (!href.startsWith("mai://")) return;
  e.preventDefault();
  e.stopPropagation();
  const raw = href.slice("mai://".length);
  const [docId, pageRaw] = raw.split("/");
  const page = Number(pageRaw || 0) || 0;
  if (!docId || !page) { showToast("Invalid citation link"); return; }
  openCitation(docId, page);
}

/* Deleting either side removes the whole turn — a question without its
   answer (or the reverse) is meaningless in the transcript and would strand
   tool_calls halfway. The server cascades via the shared turn_id. */
function del() {
  deleteTurn(props.msg.turn_id);
}

function recall() {
  recallLastUserMessage();
}

/* Fork the conversation from this answer — a new chat carrying everything
   up to here; the server switches the view to it. */
function branch() {
  branchConv(props.msg.turn_id);
}

function reEdit() {
  emit("reedit", {
    text: props.msg.originalText || "",
    pills: props.msg.originalPills || [],
    quotes: props.msg.originalQuotes || [],
  });
}
</script>

<template>
  <div class="msg" :class="[isAI ? 'ai' : 'user', { recalled: msg._recalled }]">
    <!-- Recalled placeholder: WeChat-style "You recalled a message" with re-edit -->
    <div v-if="msg._recalled" class="recalled-placeholder">
      <span>You recalled a message</span>
      <span class="reedit" @click="reEdit">Edit</span>
    </div>
    <template v-else>
    <div class="brow">
      <!-- WeChat-style failed-send mark: the send never reached the model;
           clicking resends the same text + pills -->
      <button v-if="msg._failed" class="fail" data-tip="Failed — click to resend"
              @click="retrySend(msg)" v-html="SVG_FAIL"></button>
      <div class="bubble">
      <template v-if="isAI && orderedParts.length">
        <template v-for="(part, i) in orderedParts" :key="i">
          <div v-if="part.type === 'tool'" class="tool-wrap" :class="{ open: part._open }">
            <div class="tool-step" :class="'step-' + (part.status || 'run')" @click="toggleTool(part)">
              <span class="step-dot"></span>
              <span class="step-label">{{ part.display?.label || part.tool }}</span>
              <span v-if="part.display?.param" class="step-file">{{ part.display.param }}</span>
              <span v-if="part.status === 'error' && part.error" class="step-err">{{ part.error }}</span>
              <span class="step-mark">{{ part.status === "run" ? "…" : part.status === "ok" ? "✓" : "✗" }}</span>
              <span class="step-chev" :class="{ open: part._open }" v-html="SVG_CHEV"></span>
            </div>
            <div v-if="part._open" class="tool-detail">
              <template v-if="part.arguments && Object.keys(part.arguments).length">
                <div class="detail-head">Arguments</div>
                <div class="args-box">
                  <div v-for="(v, k) in part.arguments" :key="k" class="arg-row">
                    <div class="arg-key">{{ argLabel(k) }}</div>
                    <div class="arg-val" :class="{ mono: isPathLike(v) }">{{ argValue(v) }}</div>
                  </div>
                </div>
              </template>
              <template v-if="part.result != null && part.result !== ''">
                <div class="detail-head">{{ part.status === 'error' ? 'Error' : 'Result' }}</div>
                <pre>{{ resultText(part) }}</pre>
              </template>
              <template v-else-if="part.status === 'error' && part.error">
                <div class="detail-head">Error</div>
                <pre>{{ part.error }}</pre>
              </template>
              <div v-else-if="part.status === 'run'" class="detail-empty">Running…</div>
            </div>
          </div>
          <div v-else class="md" @click="onMarkdownClick" v-html="partHtml(part)"></div>
        </template>
      </template>
      <template v-else>
        <div v-if="isAI && msg.tools && msg.tools.length" class="tool-block">
          <div class="tool-block-head">AGENT</div>
          <div v-for="t in msg.tools" :key="t.call_id" class="tool-wrap" :class="{ open: t._open }">
            <div class="tool-step" :class="'step-' + (t.status || 'run')" @click="toggleTool(t)">
              <span class="step-dot"></span>
              <span class="step-label">{{ t.display?.label || t.tool }}</span>
              <span v-if="t.display?.param" class="step-file">{{ t.display.param }}</span>
              <span v-if="t.status === 'error' && t.error" class="step-err">{{ t.error }}</span>
              <span class="step-mark">{{ t.status === "run" ? "…" : t.status === "ok" ? "✓" : "✗" }}</span>
              <span class="step-chev" :class="{ open: t._open }" v-html="SVG_CHEV"></span>
            </div>
            <div v-if="t._open" class="tool-detail">
              <template v-if="t.arguments && Object.keys(t.arguments).length">
                <div class="detail-head">Arguments</div>
                <div class="args-box">
                  <div v-for="(v, k) in t.arguments" :key="k" class="arg-row">
                    <div class="arg-key">{{ argLabel(k) }}</div>
                    <div class="arg-val" :class="{ mono: isPathLike(v) }">{{ argValue(v) }}</div>
                  </div>
                </div>
              </template>
              <template v-if="t.result != null && t.result !== ''">
                <div class="detail-head">{{ t.status === 'error' ? 'Error' : 'Result' }}</div>
                <pre>{{ resultText(t) }}</pre>
              </template>
              <template v-else-if="t.status === 'error' && t.error">
                <div class="detail-head">Error</div>
                <pre>{{ t.error }}</pre>
              </template>
              <div v-else-if="t.status === 'run'" class="detail-empty">Running…</div>
            </div>
          </div>
        </div>
        <div v-if="isAI" class="md" @click="onMarkdownClick" v-html="html"></div>
        <span v-else-if="utext" class="utext">{{ utext }}</span>
      </template>
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
      <button v-if="isLastUser && !msg._streaming && !msg._failed" class="recall-btn" data-tip="Recall" @click="recall" v-html="SVG_RECALL"></button>
      <button v-if="isAI && !msg._streaming" data-tip="Copy" @click="copy" v-html="SVG_COPY"></button>
      <button v-if="isAI && !msg._streaming && msg.turn_id" data-tip="Branch from here"
              @click="branch" v-html="SVG_BRANCH"></button>
      <button v-if="!msg._streaming && msg.turn_id" class="del" data-tip="Delete turn"
              @click="del" v-html="SVG_TRASH"></button>
    </div>
    </template>
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
/* Recalled placeholder — WeChat-style */
.recalled-placeholder {
  text-align: center;
  padding: 6px 0;
  font: 11px var(--mono);
  color: var(--text-4);
}
.recalled-placeholder .reedit {
  color: var(--brand);
  cursor: pointer;
  margin-left: 8px;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.recalled-placeholder .reedit:hover {
  color: var(--text);
}
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
.md :deep(a) { color: var(--brand); cursor: pointer; }
.md :deep(.cite-badge) {
  display: inline-flex; align-items: center; gap: 0; max-width: min(220px, 100%);
  vertical-align: middle; overflow: hidden; border-radius: 7px;
  border: 1px solid var(--line); text-decoration: none; font-size: 0; line-height: 1;
  transform: translateY(-1px);
}
.md :deep(.cite-badge .cite-file) {
  display: inline-flex; align-items: center; height: 18px; max-width: 145px; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  padding: 0 6px; color: var(--text-2); background: var(--bg-raise);
  font: 10px var(--mono);
}
.md :deep(.cite-badge .cite-page) {
  display: inline-flex; align-items: center; height: 18px; flex: none; padding: 0 6px;
  color: #061016; background: var(--brand); font: 700 10px var(--mono);
}
.md :deep(table) { border-collapse: collapse; margin: 0 0 8px; font-size: 11.5px; }
.md :deep(th), .md :deep(td) { border: 1px solid var(--border); padding: 3px 8px; }
.md :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 8px 0; }
/* ── Tool step rows (GitHub Actions badge-style) ── */
.tool-block { margin: 12px 0; }
.tool-block-head {
  font: 700 8.5px var(--mono); letter-spacing: 1.5px; text-transform: uppercase;
  color: var(--text-4); margin-bottom: 4px; padding-left: 2px;
}
.tool-step {
  display: flex; align-items: center; gap: 10px;
  padding: 5px 10px;
  border: 1px solid var(--border); border-radius: 5px;
  background: var(--bg-raise);
  font: 11px/1.5 var(--sans);
  cursor: pointer;
}
.tool-wrap { margin: 6px 0; }
.tool-step:hover { background: var(--bg-hover); }
.tool-wrap.open .tool-step { border-radius: 5px 5px 0 0; }
.step-chev {
  display: inline-flex; flex: none; color: var(--text-4);
  transition: transform .15s ease;
}
.step-chev :deep(svg) { width: 11px; height: 11px; }
.step-chev.open { transform: rotate(90deg); }
/* Expanded inspector: what the call sent, what came back */
.tool-detail {
  border: 1px solid var(--border); border-top: none;
  border-radius: 0 0 5px 5px;
  background: var(--bg);
  padding: 8px 10px;
}
.detail-head {
  font: 700 8.5px var(--mono); letter-spacing: 1.2px; text-transform: uppercase;
  color: var(--text-4); margin: 8px 0 3px;
}
.detail-head:first-child { margin-top: 0; }
/* Arguments as labeled rows — keys in a small caption, values in a reading
   face (paths keep mono). No braces, no quotes: it should read like a form. */
.args-box {
  background: var(--bg-raise); border: 1px solid var(--border); border-radius: 4px;
  padding: 8px 10px;
  display: flex; flex-direction: column; gap: 8px;
  max-height: 220px; overflow: auto;
}
.arg-row + .arg-row { border-top: 1px solid var(--border-soft); padding-top: 8px; }
.arg-key {
  font: 700 8.5px var(--mono); letter-spacing: 1px; text-transform: uppercase;
  color: var(--text-4); margin-bottom: 2px;
}
.arg-val {
  font: 11px/1.55 var(--sans); color: var(--text-2);
  white-space: pre-wrap; word-break: break-word;
}
.arg-val.mono { font: 11px/1.55 var(--mono); color: var(--blue); }
.tool-detail pre {
  margin: 0; padding: 8px 10px;
  background: var(--bg-raise); border: 1px solid var(--border); border-radius: 4px;
  max-height: 220px; overflow: auto;
  font: 11px/1.55 var(--mono); color: var(--text-2);
  white-space: pre-wrap; word-break: break-word;
}
.detail-empty { font: 11px var(--mono); color: var(--text-4); }
.step-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
  background: var(--border-soft);
}
.step-run .step-dot {
  background: var(--amber);
  animation: pulse-dot 1.2s ease-in-out infinite;
}
.step-ok  .step-dot { background: var(--brand); }
.step-error .step-dot { background: var(--red); }

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%      { opacity: 0.35; transform: scale(1.25); }
}
.step-file {
  color: var(--blue);
  background: rgba(88,166,255,.1);
  padding: 1px 6px; border-radius: 3px;
  font: 10.5px var(--mono);
  max-width: 180px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  flex-shrink: 1;
}
.step-label {
  color: var(--text);
  font-weight: 500;
}
.step-mark {
  margin-left: auto;
  font-size: 10px;
  width: 14px; text-align: center; flex-shrink: 0;
}

@keyframes blink-mark {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.25; }
}
.step-run .step-mark   { color: var(--amber); animation: blink-mark 1.2s step-end infinite; }
.step-ok .step-mark    { color: var(--brand); }
.step-error .step-mark { color: var(--red); }
.step-err {
  font-size: 10px; color: var(--red);
  max-width: 140px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* Tool trace reuses the global .trace look from the mock era */
.trace-inline { margin: 6px 0 8px; }
.param { color: var(--text-3); }
.errx { color: var(--red); }
</style>
