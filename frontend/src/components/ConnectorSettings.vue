<script setup>
/* Connector settings — configure IM bots (Slack, Feishu/Lark, DingTalk)
   and browse their conversation logs.

   Four views toggled by `view` ref:
   A. List    — platform cards (connected → click to view chats,
                not connected → click to configure).
   B. Config  — per-platform credential form.
   C. Loading — brief spinner during mock connect.
   D. Chat    — read-only conversation bubbles grouped by day.

   All data is mock — real API integration comes later. */
import { ref, nextTick } from "vue";

/* ---- platform definitions ------------------------------------------------ */
const PLATFORMS = [
  {
    key: "slack",
    name: "Slack",
    desc: "Slack workspace bot",
    icon: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zM15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z"/></svg>`,
    fields: [
      { key: "token", label: "Bot Token", placeholder: "xoxb-...", hint: "Found in your Slack app settings under OAuth & Permissions.", required: true },
      { key: "channel", label: "Default Channel", placeholder: "#mortgage-work", hint: "The channel the bot will monitor.", required: false },
    ],
  },
  {
    key: "lark",
    name: "飞书 Lark",
    desc: "Feishu / Lark custom bot",
    icon: `<svg viewBox="0 0 48 48" fill="currentColor" fill-rule="evenodd" clip-rule="evenodd"><path d="M41.072 5.994L3.31 16.52l9.075 9.294l8.414.146l9.683-9.44q-.384-.787-.384-1.318c0-.794.311-1.422.796-1.868q1.244-1.145 2.994-.342zm1.03.734L31.578 44.49l-9.294-9.075L22.137 27l9.375-9.518a2.54 2.54 0 0 0 1.664.495c.902-.05 1.485-.596 1.759-.917a2.35 2.35 0 0 0 .567-1.649a2.57 2.57 0 0 0-.52-1.464z"/></svg>`,
    fields: [
      { key: "appId", label: "App ID", placeholder: "cli_a1b2c3d4", hint: "Found in Feishu Open Platform → your app → Credentials.", required: true },
      { key: "appSecret", label: "App Secret", placeholder: "••••••••••••", hint: "Found next to App ID in the same page.", required: true },
    ],
  },
  {
    key: "dingtalk",
    name: "钉钉 DingTalk",
    desc: "DingTalk robot webhook",
    icon: `<svg viewBox="0 0 1024 1024" fill="currentColor"><path d="M573.7 252.5C422.5 197.4 201.3 96.7 201.3 96.7c-15.7-4.1-17.9 11.1-17.9 11.1c-5 61.1 33.6 160.5 53.6 182.8c19.9 22.3 319.1 113.7 319.1 113.7S326 357.9 270.5 341.9c-55.6-16-37.9 17.8-37.9 17.8c11.4 61.7 64.9 131.8 107.2 138.4c42.2 6.6 220.1 4 220.1 4s-35.5 4.1-93.2 11.9c-42.7 5.8-97 12.5-111.1 17.8c-33.1 12.5 24 62.6 24 62.6c84.7 76.8 129.7 50.5 129.7 50.5c33.3-10.7 61.4-18.5 85.2-24.2L565 743.1h84.6L603 928l205.3-271.9H700.8l22.3-38.7c.3.5.4.8.4.8S799.8 496.1 829 433.8l.6-1h-.1c5-10.8 8.6-19.7 10-25.8c17-71.3-114.5-99.4-265.8-154.5"/></svg>`,
    fields: [
      { key: "appKey", label: "App Key", placeholder: "dingoa...", hint: "Found in DingTalk Open Platform → your app → Credentials & Basic Info.", required: true },
      { key: "appSecret", label: "App Secret", placeholder: "••••••••••••", hint: "Found next to App Key.", required: true },
    ],
  },
];

/* ---- mock conversation data ---------------------------------------------- */
const MOCK_CHATS = {
  slack: [
    { day: "Today", messages: [
      { from: "bot", sender: "Slack Bot", time: "2:14 PM", text: "New message from #client-michael-thompson:" },
      { from: "me", sender: "You", time: "2:15 PM", text: "Got it, I'll review the appraisal docs and get back to them." },
      { from: "bot", sender: "Slack Bot", time: "2:16 PM", text: "@sarah asked: Are we still on for the closing on the 28th? Title company needs confirmation by EOD Friday." },
      { from: "me", sender: "You", time: "2:20 PM", text: "Yes, confirmed. I'll send the closing disclosure to title today." },
    ]},
    { day: "Yesterday", messages: [
      { from: "bot", sender: "Slack Bot", time: "4:30 PM", text: "Reminder: James Whitfield hasn't uploaded his bank statements yet. The file is 12 days from conditional approval." },
      { from: "me", sender: "You", time: "4:32 PM", text: "Can you send him a nudge through the bot?" },
      { from: "bot", sender: "Slack Bot", time: "4:32 PM", text: "Done. Message sent to James Whitfield via Slack DM." },
    ]},
  ],
  lark: [
    { day: "Today", messages: [
      { from: "bot", sender: "飞书 Bot", time: "11:02 AM", text: `Sofia Reyes 在客户群里发了一条消息："上周说的收入证明我已经上传了，麻烦看一下还需要补充什么。"` },
      { from: "me", sender: "You", time: "11:15 AM", text: "收到，我让助理检查一下文档清单。" },
      { from: "bot", sender: "飞书 Bot", time: "11:16 AM", text: "系统检测到 income/ 目录新增了一份文件「sofia-bank-statement-aug.pdf」，已自动归档。" },
    ]},
    { day: "Aug 10", messages: [
      { from: "bot", sender: "飞书 Bot", time: "9:00 AM", text: "今日待办提醒：3 位客户需要在本周内完成贷款条件清除。" },
      { from: "me", sender: "You", time: "9:05 AM", text: "把名单发给我。" },
      { from: "bot", sender: "飞书 Bot", time: "9:05 AM", text: "1. Thomas Wright — 评估报告待补\n2. Wei Chen — 保险确认函待补\n3. Carlos Mendez — 收入证明更新" },
    ]},
  ],
  dingtalk: [
    { day: "Today", messages: [
      { from: "bot", sender: "钉钉 Bot", time: "3:45 PM", text: "Robert Chang 在群里询问：贷款审批进度怎么样了？还需要我做什么吗？" },
      { from: "me", sender: "You", time: "3:50 PM", text: "审批已经到了 underwriting 阶段，目前还差一份房屋保险报价单。你的保险经纪人有发给你吗？" },
      { from: "bot", sender: "钉钉 Bot", time: "3:52 PM", text: "Robert Chang 回复：今天下午就让他发过来。" },
    ]},
  ],
};

/* ---- reactive state ------------------------------------------------------ */
const view = ref("list");           // list | config | connecting | chat
const connected = ref(new Set());   // keys of connected platforms
const activePlatform = ref("");     // key for config or chat view
const fieldValues = ref({});        // { fieldKey: value } during config
const fieldErrors = ref(new Set()); // field keys with red border

/* ---- helpers ------------------------------------------------------------- */
function platformByKey(key) {
  return PLATFORMS.find(p => p.key === key);
}

/* ---- actions ------------------------------------------------------------- */
function onCardClick(key) {
  if (connected.value.has(key)) showChat(key);
  else showConfig(key);
}

function showConfig(key) {
  activePlatform.value = key;
  fieldValues.value = {};
  fieldErrors.value = new Set();
  view.value = "config";
  // Focus the first required field
  const p = platformByKey(key);
  if (p) {
    const firstReq = p.fields.find(f => f.required);
    if (firstReq) {
      nextTick(() => {
        const el = document.querySelector(`[data-field="${firstReq.key}"]`);
        if (el) el.focus();
      });
    }
  }
}

function showChat(key) {
  activePlatform.value = key;
  view.value = "chat";
}

function backToList() {
  view.value = "list";
}

function tryConnect() {
  const p = platformByKey(activePlatform.value);
  if (!p) return;
  // Validate required fields
  const errs = new Set();
  p.fields.forEach(f => {
    if (f.required && !(fieldValues.value[f.key] || "").trim()) {
      errs.add(f.key);
    }
  });
  fieldErrors.value = errs;
  if (errs.size) return;
  // Mock connecting
  view.value = "connecting";
  setTimeout(() => {
    connected.value = new Set([...connected.value, activePlatform.value]);
    view.value = "chat";
  }, 1500);
}

function disconnectCurrent() {
  connected.value = new Set([...connected.value].filter(k => k !== activePlatform.value));
  view.value = "list";
}
</script>

<template>
  <div class="viewer">

    <!-- ===== A. Platform list ===== -->
    <template v-if="view === 'list'">
      <div class="panel-header">
        <span class="header-title">Connectors</span>
      </div>
      <div class="connector-list">
        <div class="list-intro">
          Connect your messaging platforms so clients can reach you through
          their preferred channel. Conversations are synced here for your records.
        </div>
        <div
          v-for="p in PLATFORMS" :key="p.key"
          class="c-card"
          @click="onCardClick(p.key)"
        >
          <div class="c-icon" v-html="p.icon"></div>
          <div class="c-body">
            <div class="c-name">{{ p.name }}</div>
            <div class="c-desc">{{ connected.has(p.key) ? 'Tap to view conversations' : p.desc }}</div>
          </div>
          <div class="c-right">
            <span class="c-status-mini" :class="{ on: connected.has(p.key) }">
              {{ connected.has(p.key) ? '● Connected' : 'Not connected' }}
            </span>
            <span class="c-chevron">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
            </span>
          </div>
        </div>
      </div>
    </template>

    <!-- ===== B. Config form ===== -->
    <template v-else-if="view === 'config'">
      <div class="panel-header">
        <div class="panel-header-left">
          <button class="back-btn" @click="backToList">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <span class="header-title">Connect {{ platformByKey(activePlatform)?.name }}</span>
        </div>
      </div>
      <div class="config-body">
        <div class="config-form">
          <template v-if="platformByKey(activePlatform)">
            <div class="config-platform-banner">
              <div class="c-icon sm" v-html="platformByKey(activePlatform).icon"></div>
              <div>
                <div class="c-name lg">{{ platformByKey(activePlatform).name }}</div>
                <div class="c-desc">{{ platformByKey(activePlatform).desc }}</div>
              </div>
            </div>
            <div v-for="f in platformByKey(activePlatform).fields" :key="f.key" class="field-group">
              <div class="field-label">
                {{ f.label }}
                <span v-if="f.required" class="required">*</span>
              </div>
              <input
                class="field-input"
                :class="{ error: fieldErrors.has(f.key) }"
                :data-field="f.key"
                v-model="fieldValues[f.key]"
                :placeholder="f.placeholder"
                :type="f.key.toLowerCase().includes('secret') ? 'password' : 'text'"
                autocomplete="off"
                @input="fieldErrors.delete(f.key)"
              />
              <div v-if="f.hint" class="field-hint">{{ f.hint }}</div>
            </div>
            <div class="field-actions">
              <button class="btn-primary" @click="tryConnect">Connect</button>
              <button class="btn-secondary" @click="backToList">Cancel</button>
            </div>
          </template>
        </div>
      </div>
    </template>

    <!-- ===== C. Connecting ===== -->
    <template v-else-if="view === 'connecting'">
      <div class="connecting">
        <div class="fb-spin"></div>
        Connecting to {{ platformByKey(activePlatform)?.name }}…
      </div>
    </template>

    <!-- ===== D. Chat (read-only) ===== -->
    <template v-else-if="view === 'chat'">
      <div class="panel-header">
        <div class="panel-header-left">
          <button class="back-btn" @click="backToList">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <div class="c-icon xs" v-html="platformByKey(activePlatform)?.icon"></div>
          <span class="header-title">{{ platformByKey(activePlatform)?.name }}</span>
          <span class="status-tag"><span class="dot"></span>Connected</span>
        </div>
        <button class="action-btn danger" @click="disconnectCurrent">Disconnect</button>
      </div>
      <div class="chat-body">
        <template v-if="(MOCK_CHATS[activePlatform] || []).length">
          <template v-for="group in MOCK_CHATS[activePlatform]" :key="group.day">
            <div class="chat-day">{{ group.day }}</div>
            <div
              v-for="(m, i) in group.messages" :key="i"
              class="cmsg" :class="m.from"
            >
              <div class="cmsg-avatar connector-msg-avatar" v-html="m.from === 'me'
                ? `<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2'/><circle cx='12' cy='7' r='4'/></svg>`
                : platformByKey(activePlatform)?.icon
              "></div>
              <div class="cmsg-content">
                <span class="cmsg-sender">{{ m.sender }} · {{ m.time }}</span>
                <div class="cmsg-bubble">{{ m.text }}</div>
              </div>
            </div>
          </template>
        </template>
        <div v-else class="chat-empty">
          <div class="chat-empty-icon">💬</div>
          <div>No conversations yet</div>
          <div class="chat-empty-sub">Messages will appear here when clients reach out</div>
        </div>
      </div>
    </template>

  </div>
</template>

<style scoped>
/* height: 100% fills .settings-content so the panel header + scrollable
   body stack correctly even though the parent is not a flex container. */
.viewer {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ---- Panel header (shared by all views) ---- */
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  flex-shrink: 0;
}
.panel-header-left { display: flex; align-items: center; gap: 10px; }
.back-btn {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  background: none; border: 1px solid transparent;
  color: var(--text-4); cursor: pointer;
  transition: color .12s, border-color .12s;
}
.back-btn:hover { color: var(--text-2); border-color: var(--border-soft); }
.back-btn svg { width: 16px; height: 16px; }
.header-title { font: 600 13px var(--sans); color: var(--text-2); }
.status-tag {
  display: inline-flex; align-items: center; gap: 5px;
  font: 600 10px var(--mono);
  padding: 3px 8px;
  background: var(--tint-green); color: var(--green);
}
.status-tag .dot { width: 5px; height: 5px; background: var(--green); border-radius: 50%; }
.action-btn {
  font: 400 11px var(--mono);
  padding: 5px 12px;
  background: var(--bg-raise); border: 1px solid var(--border-soft);
  color: var(--text-3); cursor: pointer;
  transition: all .12s;
}
.action-btn:hover { color: var(--text-2); border-color: var(--text-4); }
.action-btn.danger:hover { color: var(--red); border-color: rgba(235,54,28,.3); }

/* ---- List view ---- */
.connector-list {
  flex: 1; overflow-y: scroll;
  padding: 20px;
}
.list-intro {
  font: 400 12px var(--sans); color: var(--text-4);
  line-height: 1.6; margin-bottom: 18px;
  max-width: 480px;
}
.c-card {
  display: flex; align-items: center; gap: 14px;
  padding: 16px 18px;
  background: var(--bg-panel); border: 1px solid var(--border);
  margin-bottom: 8px; cursor: pointer;
  transition: border-color .15s, background .15s;
}
.c-card:hover { border-color: var(--border-soft); background: var(--bg-hover); }
.c-icon {
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  background: var(--bg-raise); border: 1px solid var(--border-soft);
  flex-shrink: 0;
}
.c-icon.sm { width: 32px; height: 32px; }
.c-icon.xs { width: 24px; height: 24px; }
.c-icon :deep(svg) { width: 20px; height: 20px; }
.c-icon.sm :deep(svg) { width: 18px; height: 18px; }
.c-icon.xs :deep(svg) { width: 14px; height: 14px; }
.c-body { flex: 1; min-width: 0; }
.c-name { font: 600 13px var(--sans); color: var(--text); }
.c-name.lg { font-size: 14px; }
.c-desc { font: 400 11px var(--sans); color: var(--text-4); margin-top: 2px; }
.c-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.c-status-mini { font: 400 10px var(--mono); color: var(--text-4); }
.c-status-mini.on { color: var(--green); }
.c-chevron { color: var(--text-4); display: flex; }
.c-chevron svg { width: 16px; height: 16px; }

/* ---- Config form ---- */
.config-body { flex: 1; overflow-y: scroll; padding: 24px 20px; }
.config-form { max-width: 480px; }
.config-platform-banner {
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 24px;
}
.field-group { margin-bottom: 18px; }
.field-label {
  font: 600 11px var(--mono); color: var(--text-3);
  margin-bottom: 6px; display: flex; align-items: center; gap: 6px;
}
.field-label .required { color: var(--red); font-weight: 400; }
.field-hint {
  font: 400 10.5px var(--sans); color: var(--text-4);
  margin-top: 4px; line-height: 1.5;
}
.field-input {
  width: 100%; padding: 8px 10px;
  background: var(--bg-hover); border: 1px solid var(--border);
  color: var(--text); font: 400 12.5px var(--mono);
  outline: none; transition: border-color .15s;
}
.field-input:focus { border-color: var(--brand); }
.field-input::placeholder { color: var(--text-4); }
.field-input.error { border-color: var(--red); }
.field-actions { display: flex; gap: 10px; margin-top: 24px; }
.btn-primary {
  font: 600 12px var(--sans); padding: 8px 24px;
  background: var(--brand); color: var(--on-brand);
  border: none; cursor: pointer;
  transition: filter .15s;
}
.btn-primary:hover { filter: brightness(1.1); }
.btn-secondary {
  font: 400 12px var(--sans); padding: 8px 20px;
  background: var(--bg-raise); border: 1px solid var(--border-soft);
  color: var(--text-3); cursor: pointer;
  transition: all .12s;
}
.btn-secondary:hover { color: var(--text-2); border-color: var(--text-4); }

/* ---- Connecting ---- */
.connecting {
  flex: 1; display: flex; align-items: center; justify-content: center;
  gap: 10px; color: var(--text-3); font-size: 13px;
}
.fb-spin {
  width: 16px; height: 16px; border-radius: 50%;
  border: 2px solid var(--border); border-top-color: var(--brand);
  animation: fb-rot .7s linear infinite;
}
@keyframes fb-rot { to { transform: rotate(360deg); } }

/* ---- Chat view ---- */
.chat-body { flex: 1; overflow-y: scroll; padding: 20px; }
.chat-day {
  font: 400 10px var(--mono); color: var(--text-4);
  text-align: center; margin: 16px 0 12px;
  position: relative;
}
.chat-day::before, .chat-day::after {
  content: ""; position: absolute; top: 50%;
  width: calc(50% - 50px); height: 1px; background: var(--border);
}
.chat-day::before { left: 0; }
.chat-day::after { right: 0; }
/* fit-content so short bubbles don't stretch to 70%, and margin-left:auto
   on .me properly right-aligns the whole row */
.cmsg {
  display: flex; gap: 10px; margin-bottom: 14px;
  width: fit-content; max-width: 70%;
}
.cmsg.me { flex-direction: row-reverse; margin-left: auto; }
.cmsg-avatar {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  background: var(--bg-raise); border: 1px solid var(--border-soft);
  flex-shrink: 0; overflow: hidden;
}
.cmsg-avatar :deep(svg) { width: 16px; height: 16px; }
.cmsg.me .cmsg-avatar {
  background: var(--tint-green); border-color: rgba(60,215,66,.15);
}
.cmsg-content { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.cmsg-sender { font: 600 10px var(--sans); color: var(--text-4); }
.cmsg-bubble {
  font: 400 12.5px var(--sans); color: var(--text);
  background: var(--bg-panel); border: 1px solid var(--border);
  padding: 8px 12px; line-height: 1.55;
  white-space: pre-wrap; word-break: break-word;
}
.cmsg.me .cmsg-bubble {
  background: rgba(60,215,66,.05);
  border-color: rgba(60,215,66,.1);
}

/* ---- Chat empty state ---- */
.chat-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  color: var(--text-4); font-size: 13px; gap: 6px;
  padding: 40px;
}
.chat-empty-icon { font-size: 24px; opacity: .25; margin-bottom: 4px; }
.chat-empty-sub { font-size: 11px; }
</style>

<!-- Non-scoped: v-html injected SVGs don't carry the data-v attribute,
     so :deep() from the scoped block above can't reliably reach them.
     These rules constrain every SVG inside .connector-* containers. -->
<style>
.connector-msg-avatar svg { width: 16px; height: 16px; display: block; }
.connector-icon svg { display: block; }
</style>
