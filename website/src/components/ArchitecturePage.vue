<template>
  <div class="hero-region">
    <SiteHeader />
  </div>
  <main class="arch-page">
    <div class="shell">

      <!-- ── Page intro ── -->
      <div class="arch-head">
        <p class="section-eyebrow"><span class="dot"></span> System Design</p>
        <h1>Architecture</h1>
        <p class="arch-lede">
          Five layers, three local processes, one git repo. A desktop
          workbench where the UI, the agents, and the platform services
          each live in their own boundary &mdash; connected by well-defined
          channels, never tangled.
        </p>
      </div>

      <!-- ── Mini stack diagram ── -->
      <div class="stack-diagram">
        <div
          v-for="l in stackLayers"
          :key="l.num"
          class="stack-block"
          @click="scrollToLayer(l.num)"
        >
          <span class="stack-num">{{ l.num }}</span>
          <span class="stack-label">{{ l.label }}</span>
          <span class="stack-hint">{{ l.hint }}</span>
        </div>
      </div>

      <!-- ── The vertical spine + all layers ── -->
      <div class="spine">

        <!-- ══════ Layer 01: Frontend ══════ -->
        <section class="layer-container" id="layer-01">
          <div class="layer-header">
            <span class="lh-num">01</span>
            <span class="lh-name">Frontend</span>
            <span class="lh-tech">Vue 3 + Vite SPA inside pywebview</span>
          </div>
          <div class="layer-content">
            <div class="layer-cards">
              <div class="acard">
                <h3>Native Shell</h3>
                <p class="acard-file">app.py</p>
                <ul>
                  <li>pywebview desktop window (macOS Cocoa / Windows WebView2)</li>
                  <li><b>Api</b> class &mdash; JS bridge for workspace CRUD, file ops, settings</li>
                  <li>Spawns and reaps all child processes on startup / exit</li>
                  <li>Connector gateway lifecycle &mdash; <a href="https://github.com/zhixiangxue/linc" target="_blank" rel="noopener" class="oss-badge">linc</a></li>
                  <li>macOS branding, Windows dark-chrome theming</li>
                </ul>
              </div>
              <div class="acard">
                <h3>Frontend SPA</h3>
                <p class="acard-file">frontend/src/</p>
                <ul>
                  <li><b>ActivityBar</b> &mdash; Clients, Products, Connectors views</li>
                  <li><b>SideBar</b> &mdash; client list, client tree, product tree</li>
                  <li><b>CenterArea</b> &mdash; doc viewer, PDF viewer, text editor</li>
                  <li><b>ChatPanel</b> &mdash; AI chat with attachments and citations</li>
                  <li><b>StatusBar</b> &mdash; sync state, indexing state</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <div class="layer-interface">
          <span class="iface-line"></span>
          <span class="iface-label">
            <span class="iface-tag">JS Bridge</span> window.pywebview.api.*
            <span class="iface-sep">/</span>
            <span class="iface-tag">WebSocket</span> ws://127.0.0.1:8791/ws
          </span>
          <span class="iface-line"></span>
        </div>

        <!-- ══════ Layer 02: Backend Services ══════ -->
        <section class="layer-container" id="layer-02">
          <div class="layer-header">
            <span class="lh-num">02</span>
            <span class="lh-name">Backend Services</span>
            <span class="lh-tech">Three local processes, spawned by app.py</span>
          </div>
          <div class="layer-content">
            <div class="layer-cards three">
              <div class="acard">
                <h3>Work Repository</h3>
                <p class="acard-file">workrepo.py</p>
                <ul>
                  <li>Git-managed clone at ~/MortgageWork/</li>
                  <li><b>Sync Engine</b> &mdash; save, commit, push (3s debounce)</li>
                  <li>File operations: create, rename, move, copy, delete, upload</li>
                  <li>Watchdog observer auto-detects external file changes</li>
                  <li>Offline mode &mdash; commits queue locally, push on reconnect</li>
                </ul>
                <div class="acard-sub">
                  <span class="sub-label">Same process</span>
                  <ul>
                    <li>docindex &mdash; content-addressed file index</li>
                    <li>index/ &mdash; RAG + KG indexing pipeline</li>
                    <li>skills_manager &mdash; skill market (git repo as registry)</li>
                    <li>connector_service &mdash; <a href="https://github.com/zhixiangxue/linc" target="_blank" rel="noopener" class="oss-badge">linc</a> gateway lifecycle</li>
                  </ul>
                </div>
              </div>
              <div class="acard">
                <h3>Agent Service</h3>
                <p class="acard-file">agent_service.py</p>
                <ul>
                  <li>FastAPI + WebSocket server on :8791</li>
                  <li>Conversation persistence (JSONL per conversation)</li>
                  <li>Model to credentials resolution (settings.yaml)</li>
                </ul>
                <div class="acard-sub">
                  <span class="sub-label">Runs four agents</span>
                  <ul>
                    <li><b>QAAgent</b> &mdash; interactive mortgage QA (chat brain)</li>
                    <li><b>clerk</b> &mdash; generates ai/profile.ai per client</li>
                    <li><b>mem</b> &mdash; extracts memories from conversations</li>
                    <li><b>im</b> &mdash; auto-replies to IM platforms</li>
                  </ul>
                </div>
              </div>
              <div class="acard">
                <h3>Viewer Servers</h3>
                <p class="acard-file">browser/</p>
                <ul>
                  <li>Four FastAPI servers, spawned as child processes</li>
                  <li>Read-only data browsers, embedded as iframes</li>
                  <li>Loopback only (127.0.0.1)</li>
                </ul>
                <div class="acard-sub">
                  <span class="sub-label">Instances</span>
                  <ul>
                    <li>falkordb_viewer :8787</li>
                    <li>rqlite_viewer :9090</li>
                    <li>qdrant_viewer :8789</li>
                    <li>redis_viewer :8790</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </section>

        <div class="layer-interface">
          <span class="iface-line"></span>
          <span class="iface-label">
            <span class="iface-tag">HTTP</span> REST API calls
            <span class="iface-sep">/</span>
            <span class="iface-tag">SDK</span> in-process imports
          </span>
          <span class="iface-line"></span>
        </div>

        <!-- ══════ Layer 03: Agent Cognition ══════ -->
        <section class="layer-container" id="layer-03">
          <div class="layer-header">
            <span class="lh-num">03</span>
            <span class="lh-name">Agent Cognition</span>
            <span class="lh-tech">
              <a href="https://github.com/zhixiangxue/chak-ai" target="_blank" rel="noopener" class="oss-badge">chak</a> framework
              + ClaudeSkill
              + <a href="https://github.com/zhixiangxue/seeka-ai" target="_blank" rel="noopener" class="oss-badge">seeka</a> memory
            </span>
          </div>
          <div class="layer-content">
            <div class="layer-cards four">
              <div class="acard">
                <h3>Agent Tools</h3>
                <p class="acard-file">agents/tools/</p>
                <ul>
                  <li><b>FileSystem</b> &mdash; read and list files (repo-confined)</li>
                  <li><b>Pdf</b> &mdash; navigate and extract PDF content</li>
                  <li><b>Reader</b> &mdash; LLM-friendly file reading SDK: text, PDF, Office, images, video, audio (<a href="https://github.com/zhixiangxue/fyle" target="_blank" rel="noopener" class="oss-badge">fyle</a>)</li>
                  <li><b>RAG</b> &mdash; semantic search over product docs</li>
                  <li><b>KG</b> &mdash; knowledge graph queries</li>
                  <li><b>Mem</b> &mdash; <a href="https://github.com/zhixiangxue/seeka-ai" target="_blank" rel="noopener" class="oss-badge">seeka</a> memory recall</li>
                  <li><b>Git</b> &mdash; read commit history and diffs</li>
                </ul>
              </div>
              <div class="acard">
                <h3>SubAgents</h3>
                <p class="acard-file">agents/subagents/</p>
                <ul>
                  <li>Domain experts, each a <a href="https://github.com/zhixiangxue/chak-ai" target="_blank" rel="noopener" class="oss-badge">chak</a> tool wrapping a skill</li>
                  <li>IncomeAnalyzer &mdash; income calculation</li>
                  <li>CreditAnalyzer &mdash; credit report analysis</li>
                  <li>AssetAnalyzer &mdash; asset verification</li>
                  <li>DtiAnalyzer &mdash; debt-to-income ratio</li>
                  <li>LtvCltvAnalyzer &mdash; loan-to-value</li>
                  <li>EligibilityAnalyzer &mdash; eligibility check</li>
                  <li>DocChecklistAnalyzer &mdash; missing documents</li>
                  <li>PaymentAnalyzer &mdash; monthly payment</li>
                  <li>ProductFinder &mdash; product matching</li>
                  <li>Form1003Filler &mdash; uniform loan application</li>
                </ul>
              </div>
              <div class="acard">
                <h3>Skill Market</h3>
                <p class="acard-file">skills_manager.py</p>
                <ul>
                  <li>Git repo as installable skill registry</li>
                  <li>Three-layer state: present, installed, enabled</li>
                  <li>Install is <code>uv sync</code> (per-skill venv)</li>
                  <li>ClaudeSkill format (SKILL.md)</li>
                  <li>Namespaced python runners, no tool name collision</li>
                  <li>Factory builds SubAgents from enabled skills</li>
                </ul>
              </div>
              <div class="acard">
                <h3>Memory</h3>
                <p class="acard-file">
                  <a href="https://github.com/zhixiangxue/seeka-ai" target="_blank" rel="noopener" class="oss-badge">seeka</a> &mdash; .seeka/ inside the work repo
                </p>
                <ul>
                  <li>Embedded memory SDK &mdash; like SQLite, no server, zero setup</li>
                  <li><b>note()</b> &rarr; <b>dream()</b> &rarr; <b>recall()</b>: capture, extract, search</li>
                  <li><b>Extraction Skills</b> &mdash; custom extraction logic via plain Markdown</li>
                  <li><b>Automatic conflict resolution</b> &mdash; contradictions detected and resolved</li>
                  <li>Namespace isolation per client, no cross-contamination</li>
                  <li>Configurable embedding + reranking providers</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <div class="layer-interface">
          <span class="iface-line"></span>
          <span class="iface-label">
            <span class="iface-tag">HTTP</span> RAG :8000 &middot; KG :8001
            <span class="iface-sep">/</span>
            <span class="iface-tag">SDK</span> chak in-process &middot; linc Client SDK
          </span>
          <span class="iface-line"></span>
        </div>

        <!-- ══════ Layer 04: Platform Services & Gateways ══════ -->
        <section class="layer-container" id="layer-04">
          <div class="layer-header">
            <span class="lh-num">04</span>
            <span class="lh-name">Platform Services &amp; Gateways</span>
            <span class="lh-tech">Services we built and open-sourced</span>
          </div>
          <div class="layer-content">
            <div class="layer-cards four">
              <div class="acard">
                <h3>RAG Service</h3>
                <p class="acard-file">Semantic search over mortgage docs</p>
                <ul>
                  <li>Document parsing and vectorization pipeline</li>
                  <li>Two-step: upload, then async task</li>
                  <li>Content-based dedup (xxh64 doc_id)</li>
                  <li>Backed by Qdrant vector storage</li>
                </ul>
              </div>
              <div class="acard">
                <h3>KG Service</h3>
                <p class="acard-file">Knowledge graph for mortgage rules</p>
                <ul>
                  <li>Knowledge graph ingestion (zip bundles)</li>
                  <li>Product guideline to graph triples</li>
                  <li>Two-step: upload zip, then async ingest</li>
                  <li>Backed by FalkorDB via <a href="https://github.com/Zeitro/zig" target="_blank" rel="noopener" class="oss-badge">zig</a></li>
                </ul>
              </div>
              <div class="acard">
                <h3><a href="https://github.com/zhixiangxue/chak-ai" target="_blank" rel="noopener" class="oss-badge">chak</a></h3>
                <p class="acard-file">the agent's brain</p>
                <ul>
                  <li>Multi-model LLM client (18+ providers)</li>
                  <li>Pluggable context management (FIFO, Summarization, LRU)</li>
                  <li>Tool calling: functions, objects, skills, MCP</li>
                  <li>Event streaming for real-time tool observability</li>
                  <li>Keys in settings.yaml, never cross to UI</li>
                </ul>
              </div>
              <div class="acard">
                <h3><a href="https://github.com/zhixiangxue/linc" target="_blank" rel="noopener" class="oss-badge">linc</a></h3>
                <p class="acard-file">IM gateway daemon</p>
                <ul>
                  <li>One SQLite file is the contract</li>
                  <li>Slack, Feishu, DingTalk, WeCom adapters</li>
                  <li>Gateway owns connections; agent reads via Client SDK</li>
                  <li>WAL mode, two-flock coordination</li>
                  <li>im agent auto-replies through QAAgent</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <div class="layer-interface">
          <span class="iface-line"></span>
          <span class="iface-label">
            <span class="iface-tag">HTTPS</span> OpenAI-compatible API
            <span class="iface-sep">/</span>
            <span class="iface-tag">Webhook</span> IM platform callbacks
          </span>
          <span class="iface-line"></span>
        </div>

        <!-- ══════ Layer 05: External Providers ══════ -->
        <section class="layer-container" id="layer-05">
          <div class="layer-header">
            <span class="lh-num">05</span>
            <span class="lh-name">External Providers</span>
            <span class="lh-tech">Cloud platforms &mdash; keys never leave the machine</span>
          </div>
          <div class="layer-content">

            <!-- LLM providers -->
            <div class="ext-section">
              <div class="ext-head">
                <span class="ext-label">LLM Providers</span>
                <span class="ext-via">routed through <a href="https://github.com/zhixiangxue/chak-ai" target="_blank" rel="noopener" class="oss-badge">chak</a></span>
              </div>
              <div class="provider-grid">
                <div class="provider-card">
                  <span class="p-name">Anthropic</span>
                  <span class="p-models">Claude Sonnet / Opus / Haiku</span>
                </div>
                <div class="provider-card">
                  <span class="p-name">OpenAI</span>
                  <span class="p-models">GPT-4o / o3 / text-embedding-3</span>
                </div>
                <div class="provider-card">
                  <span class="p-name">DeepSeek</span>
                  <span class="p-models">DeepSeek-V3 / DeepSeek-R1</span>
                </div>
                <div class="provider-card">
                  <span class="p-name">Alibaba Bailian</span>
                  <span class="p-models">Qwen-Max / Qwen-Plus / Qwen-Flash</span>
                </div>
                <div class="provider-card">
                  <span class="p-name">Google Gemini</span>
                  <span class="p-models">Gemini 2.5 Pro / Flash</span>
                </div>
                <div class="provider-card">
                  <span class="p-name">Azure OpenAI</span>
                  <span class="p-models">GPT-4o / o3 (enterprise)</span>
                </div>
                <div class="provider-card">
                  <span class="p-name">Moonshot</span>
                  <span class="p-models">Kimi K1.5</span>
                </div>
                <div class="provider-card">
                  <span class="p-name">Ollama</span>
                  <span class="p-models">Llama / Qwen (local GPU)</span>
                </div>
              </div>
            </div>

            <!-- IM platforms -->
            <div class="ext-section">
              <div class="ext-head">
                <span class="ext-label">IM Platforms</span>
                <span class="ext-via">connected through <a href="https://github.com/zhixiangxue/linc" target="_blank" rel="noopener" class="oss-badge">linc</a></span>
              </div>
              <div class="provider-grid">
                <div class="provider-card">
                  <span class="p-name">Slack</span>
                  <span class="p-models">Slack API + Socket Mode</span>
                </div>
                <div class="provider-card">
                  <span class="p-name">Feishu</span>
                  <span class="p-models">Lark OpenAPI + Event Subscription</span>
                </div>
                <div class="provider-card">
                  <span class="p-name">DingTalk</span>
                  <span class="p-models">DingTalk Open Platform</span>
                </div>
                <div class="provider-card">
                  <span class="p-name">WeCom</span>
                  <span class="p-models">WeChat Work API + Callback</span>
                </div>
              </div>
            </div>

          </div>
        </section>

      </div><!-- /spine -->

      <!-- ── Data flows ── -->
      <div class="arch-flows">
        <p class="section-eyebrow"><span class="dot"></span> Key Data Flows</p>
        <div class="flow-grid">
          <div class="flow-card">
            <h3>Chat</h3>
            <p>User &rarr; ChatPanel &rarr; WebSocket &rarr; QAAgent &rarr; chak conversation (LLM + tools: RAG, KG, FileSystem, Pdf) &rarr; streamed chunks to UI</p>
          </div>
          <div class="flow-card">
            <h3>File Sync</h3>
            <p>Edit &rarr; workrepo &rarr; disk &rarr; 3s debounce commit &rarr; push to Git &rarr; trigger RAG + KG indexing &rarr; status bar update</p>
          </div>
          <div class="flow-card">
            <h3>clerk</h3>
            <p>Git commit &rarr; clerk detects stale client &rarr; reads folder and PDFs &rarr; SubAgents (income, credit, DTI) &rarr; writes ai/profile.ai</p>
          </div>
          <div class="flow-card">
            <h3>IM Auto-Reply</h3>
            <p>IM platform &rarr; linc gateway &rarr; SQLite &rarr; im agent polls &rarr; debounce batch &rarr; QAAgent &rarr; reply via linc &rarr; IM</p>
          </div>
        </div>
      </div>

      <!-- Back link -->
      <div class="arch-back">
        <a href="#" @click.prevent="$emit('navigate', 'home')">
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M10 3L5 8l5 5"/>
          </svg>
          Back to home
        </a>
      </div>
    </div>
  </main>
  <SiteFooter />
</template>

<script setup>
import SiteHeader from './SiteHeader.vue'
import SiteFooter from './SiteFooter.vue'

defineEmits(['navigate'])

const stackLayers = [
  { num: '01', label: 'Frontend',             hint: 'Vue 3 + pywebview' },
  { num: '02', label: 'Backend Services',     hint: '3 local processes' },
  { num: '03', label: 'Agent Cognition',      hint: 'chak + seeka + skills' },
  { num: '04', label: 'Platform Services',    hint: 'RAG / KG / chak / linc' },
  { num: '05', label: 'External Providers',   hint: 'LLM + IM platforms' },
]

function scrollToLayer(num) {
  document.getElementById(`layer-${num}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<style scoped>
/* ════════════════════════════════════════════════════════════════
   ARCHITECTURE PAGE
   ════════════════════════════════════════════════════════════════ */

.arch-page { padding: 56px 0 96px; }

/* ── Page intro ── */
.arch-head { margin-bottom: 40px; max-width: 720px; }
.arch-head h1 {
  font: 700 42px/1.1 var(--sans);
  letter-spacing: -0.03em;
  margin-bottom: 14px;
}
.arch-lede {
  font-size: 15px;
  color: var(--text-2);
  line-height: 1.65;
  max-width: 580px;
}

/* ════════════════════════════════════════════════════════════════
   OSS BADGE — distinctive green pill for open-source projects
   ════════════════════════════════════════════════════════════════ */
.oss-badge {
  display: inline-block;
  font: 700 10px var(--mono);
  letter-spacing: 0.5px;
  padding: 1px 7px;
  background: rgba(60, 215, 66, 0.08);
  border: 1px solid rgba(60, 215, 66, 0.3);
  color: var(--brand);
  text-decoration: none;
  white-space: nowrap;
  transition: background 0.12s, border-color 0.12s, color 0.12s;
}
.oss-badge:hover {
  background: rgba(60, 215, 66, 0.18);
  border-color: var(--brand);
  color: #4ee855;
}

/* ════════════════════════════════════════════════════════════════
   MINI STACK DIAGRAM
   ════════════════════════════════════════════════════════════════ */
.stack-diagram {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2px;
  max-width: 420px;
  margin-bottom: 56px;
  border: 1px solid var(--border-soft);
}
.stack-block {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: var(--bg-panel);
  cursor: pointer;
  transition: background 0.15s;
  position: relative;
}
.stack-block:hover {
  background: var(--bg-hover);
}
.stack-block:hover .stack-label {
  color: var(--brand);
}
.stack-num {
  font: 700 11px var(--mono);
  letter-spacing: 1px;
  color: var(--brand);
  flex-shrink: 0;
  width: 24px;
}
.stack-label {
  font: 600 13px var(--sans);
  color: var(--text);
  letter-spacing: -0.01em;
  transition: color 0.15s;
}
.stack-hint {
  font: 400 10px var(--mono);
  color: var(--text-4);
  margin-left: auto;
  text-align: right;
}

/* ════════════════════════════════════════════════════════════════
   VERTICAL SPINE — one continuous line through all layers
   ════════════════════════════════════════════════════════════════ */
.spine {
  position: relative;
  padding-left: 32px;
}
.spine::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 1px;
  background: linear-gradient(
    to bottom,
    rgba(60,215,66,0.4) 0%,
    rgba(60,215,66,0.15) 15%,
    var(--border-soft) 30%,
    var(--border-soft) 70%,
    rgba(60,215,66,0.15) 85%,
    rgba(60,215,66,0.4) 100%
  );
}

/* ════════════════════════════════════════════════════════════════
   LAYER CONTAINER
   ════════════════════════════════════════════════════════════════ */
.layer-container {
  position: relative;
  margin-bottom: 0;
}
.layer-container::before {
  content: '';
  position: absolute;
  left: -37px;
  top: 28px;
  width: 11px;
  height: 11px;
  background: var(--bg);
  border: 2px solid var(--brand);
  z-index: 2;
}

/* Layer header bar */
.layer-header {
  display: flex;
  align-items: baseline;
  gap: 14px;
  padding: 20px 0 16px;
  flex-wrap: wrap;
}
.lh-num {
  font: 700 10px var(--mono);
  letter-spacing: 2px;
  color: var(--brand);
}
.lh-name {
  font: 700 20px var(--sans);
  letter-spacing: -0.01em;
  color: var(--text);
}
.lh-tech {
  font: 400 12px var(--mono);
  color: var(--text-4);
}

/* Layer content wrapper */
.layer-content {
  border: 1px solid var(--border);
  border-left: 2px solid var(--border-soft);
  margin-bottom: 0;
}

/* ════════════════════════════════════════════════════════════════
   LAYER INTERFACE
   ════════════════════════════════════════════════════════════════ */
.layer-interface {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 0;
}
.iface-line {
  flex: 1;
  height: 1px;
  background: var(--border);
}
.iface-label {
  font: 400 11px var(--mono);
  color: var(--text-3);
  white-space: nowrap;
}
.iface-tag {
  font: 700 8px var(--mono);
  letter-spacing: 1px;
  text-transform: uppercase;
  padding: 2px 6px;
  background: var(--bg-raise);
  color: var(--brand);
  margin-right: 6px;
}
.iface-sep {
  color: var(--text-4);
  margin: 0 4px;
}

/* ════════════════════════════════════════════════════════════════
   CARDS
   ════════════════════════════════════════════════════════════════ */
.layer-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: var(--border);
}
.layer-cards.three { grid-template-columns: 1fr 1fr 1fr; }
.layer-cards.four  { grid-template-columns: 1fr 1fr 1fr 1fr; }

.acard {
  background: var(--bg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.acard h3 {
  font: 700 13px var(--mono);
  color: var(--text);
}
.acard-file {
  font: 400 10px var(--mono);
  color: var(--text-4);
  margin-bottom: 8px;
}
.acard ul {
  list-style: none;
  font: 400 12px/1.7 var(--sans);
  color: var(--text-3);
}
.acard ul li {
  padding-left: 12px;
  position: relative;
}
.acard ul li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  width: 4px;
  height: 1px;
  background: var(--border-soft);
}
.acard ul li b { color: var(--text); font-weight: 600; }
.acard code {
  font: 400 11px var(--mono);
  background: var(--bg-raise);
  padding: 1px 4px;
  color: var(--text-2);
}

/* Card sub-section */
.acard-sub {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}
.sub-label {
  display: block;
  font: 700 8px var(--mono);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--text-4);
  margin-bottom: 8px;
}

/* ════════════════════════════════════════════════════════════════
   EXTERNAL PROVIDER SECTIONS (Layer 05)
   ════════════════════════════════════════════════════════════════ */
.ext-section {
  border-bottom: 1px solid var(--border);
}
.ext-section:last-child { border-bottom: none; }

.ext-head {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 20px;
  background: var(--bg-raise);
  border-bottom: 1px solid var(--border);
}
.ext-label {
  font: 700 11px var(--mono);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--text);
}
.ext-via {
  font: 400 11px var(--mono);
  color: var(--text-4);
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--border);
}
.provider-card {
  background: var(--bg);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.p-name {
  font: 700 13px var(--sans);
  color: var(--text);
  letter-spacing: -0.01em;
}
.p-models {
  font: 400 10px var(--mono);
  color: var(--text-4);
  line-height: 1.5;
}

/* ════════════════════════════════════════════════════════════════
   DATA FLOWS
   ════════════════════════════════════════════════════════════════ */
.arch-flows {
  margin-top: 56px;
  border-top: 1px solid var(--border);
  padding-top: 40px;
}
.flow-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  margin-top: 8px;
}
.flow-card {
  background: var(--bg);
  padding: 20px;
}
.flow-card h3 {
  font: 700 11px var(--mono);
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--brand);
  margin-bottom: 8px;
}
.flow-card p {
  font: 400 12px/1.7 var(--sans);
  color: var(--text-3);
}

/* ── Back link ── */
.arch-back {
  margin-top: 48px;
  text-align: center;
}
.arch-back a {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 600 12px var(--mono);
  color: var(--text-3);
  transition: color 0.12s;
}
.arch-back a:hover { color: var(--brand); }

/* ════════════════════════════════════════════════════════════════
   RESPONSIVE
   ════════════════════════════════════════════════════════════════ */
@media (max-width: 860px) {
  .arch-head h1 { font-size: 32px; }
  .layer-cards,
  .layer-cards.three,
  .layer-cards.four,
  .provider-grid { grid-template-columns: 1fr; }
  .flow-grid { grid-template-columns: 1fr; }
  .iface-label { white-space: normal; }
  .ext-head { flex-direction: column; align-items: flex-start; gap: 6px; }
}
</style>
