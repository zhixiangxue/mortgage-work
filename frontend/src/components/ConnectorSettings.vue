<script setup>
/* Connector settings — configure IM bots (Slack, Feishu/Lark, DingTalk)
   and browse their conversation logs.

   Five views toggled by `view` ref:
   A. List    — platform cards (configured → click to view conversations,
                not configured → click to configure).
   B. Config  — per-platform credential form.
   C. Connecting — brief spinner while saving config.
   D. Convs   — conversation list for a platform (grouped by conv_id).
   E. Chat    — read-only message bubbles for a conversation. */
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from "vue";

/* ---- platform icons (local — backend sends metadata, not SVGs) ----------- */
const PLATFORM_ICONS = {
  slack: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zM15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z"/></svg>`,
  feishu: `<svg viewBox="0 0 48 48" fill="currentColor" fill-rule="evenodd" clip-rule="evenodd"><path d="M41.072 5.994L3.31 16.52l9.075 9.294l8.414.146l9.683-9.44q-.384-.787-.384-1.318c0-.794.311-1.422.796-1.868q1.244-1.145 2.994-.342zm1.03.734L31.578 44.49l-9.294-9.075L22.137 27l9.375-9.518a2.54 2.54 0 0 0 1.664.495c.902-.05 1.485-.596 1.759-.917a2.35 2.35 0 0 0 .567-1.649a2.57 2.57 0 0 0-.52-1.464z"/></svg>`,
  dingtalk: `<svg viewBox="0 0 1024 1024" fill="currentColor"><path d="M573.7 252.5C422.5 197.4 201.3 96.7 201.3 96.7c-15.7-4.1-17.9 11.1-17.9 11.1c-5 61.1 33.6 160.5 53.6 182.8c19.9 22.3 319.1 113.7 319.1 113.7S326 357.9 270.5 341.9c-55.6-16-37.9 17.8-37.9 17.8c11.4 61.7 64.9 131.8 107.2 138.4c42.2 6.6 220.1 4 220.1 4s-35.5 4.1-93.2 11.9c-42.7 5.8-97 12.5-111.1 17.8c-33.1 12.5 24 62.6 24 62.6c84.7 76.8 129.7 50.5 129.7 50.5c33.3-10.7 61.4-18.5 85.2-24.2L565 743.1h84.6L603 928l205.3-271.9H700.8l22.3-38.7c.3.5.4.8.4.8S799.8 496.1 829 433.8l.6-1h-.1c5-10.8 8.6-19.7 10-25.8c17-71.3-114.5-99.4-265.8-154.5"/></svg>`,
  wecom: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="m17.326 8.158l-.003-.007a6.6 6.6 0 0 0-1.178-1.674c-1.266-1.307-3.067-2.19-5.102-2.417a9.3 9.3 0 0 0-2.124 0h-.001c-2.061.228-3.882 1.107-5.14 2.405a6.7 6.7 0 0 0-1.194 1.682A5.7 5.7 0 0 0 2 10.657c0 1.106.332 2.218.988 3.201l.006.01c.391.594 1.092 1.39 1.637 1.83l.983.793l-.208.875l.527-.267l.708-.358l.761.225c.467.137.955.227 1.517.29h.005q.515.06 1.026.059c.355 0 .724-.02 1.095-.06a9 9 0 0 0 1.346-.258c.095.7.43 1.337.932 1.81c-.658.208-1.352.358-2.061.436c-.442.048-.883.072-1.312.072q-.627 0-1.253-.072a10.7 10.7 0 0 1-1.861-.36l-2.84 1.438s-.29.131-.44.131c-.418 0-.702-.285-.702-.704c0-.252.067-.598.128-.84l.394-1.653c-.728-.586-1.563-1.544-2.052-2.287A7.76 7.76 0 0 1 0 10.658a7.7 7.7 0 0 1 .787-3.39a8.7 8.7 0 0 1 1.551-2.19c1.61-1.665 3.878-2.73 6.359-3.006a11.3 11.3 0 0 1 2.565 0c2.47.275 4.712 1.353 6.323 3.017a8.6 8.6 0 0 1 1.539 2.192c.466.945.769 1.937.769 2.978a3.06 3.06 0 0 0-2-.005c-.001-.644-.189-1.329-.564-2.09zm4.125 6.977l-.024-.024l-.024-.018l-.024-.018l-.096-.095a4.24 4.24 0 0 1-1.169-2.192q0-.038-.006-.075l-.006-.056l-.035-.144a1.3 1.3 0 0 0-.358-.61a1.386 1.386 0 0 0-1.957 0a1.4 1.4 0 0 0 0 1.963c.191.191.418.311.668.371c.024.012.06.012.084.012q.019 0 .041.006q.023.005.042.006a4.24 4.24 0 0 1 2.231 1.186c.048.048.096.095.131.143a.323.323 0 0 0 .466 0a.35.35 0 0 0 .036-.455m-1.05 4.37l-.025.025c-.119.096-.31.096-.453-.036a.326.326 0 0 1 0-.467c.047-.036.094-.083.141-.13l.002-.002a4.27 4.27 0 0 0 1.187-2.28q.005-.024.006-.043c0-.024 0-.06.012-.084a1.386 1.386 0 0 1 2.326-.67a1.4 1.4 0 0 1 0 1.964c-.167.18-.382.299-.608.359l-.143.036l-.057.005q-.035.006-.075.007a4.2 4.2 0 0 0-2.183 1.173l-.095.096q-.009.01-.018.024t-.018.024m-4.392-1.053l.024.024l.024.018q.015.009.024.018l.096.096a4.25 4.25 0 0 1 1.169 2.19q0 .04.006.076q.005.03.006.057l.035.143c.06.228.18.443.358.611c.537.539 1.42.539 1.957 0a1.4 1.4 0 0 0 0-1.964a1.4 1.4 0 0 0-.668-.371c-.024-.012-.06-.012-.084-.012q-.018 0-.041-.006l-.042-.006a4.25 4.25 0 0 1-2.231-1.185a1.4 1.4 0 0 1-.131-.144a.323.323 0 0 0-.466 0a.325.325 0 0 0-.036.455m1.039-4.358l.024-.024a.32.32 0 0 1 .453.035a.326.326 0 0 1 0 .467c-.047.036-.094.083-.141.13l-.002.002a4.27 4.27 0 0 0-1.187 2.281l-.006.042c0 .024 0 .06-.012.084a1.386 1.386 0 0 1-2.326.67a1.4 1.4 0 0 1 0-1.963c.166-.18.381-.3.608-.36l.143-.035q.026 0 .056-.006q.037-.005.075-.006a4.2 4.2 0 0 0 2.183-1.174l.096-.095l.018-.025z"/></svg>`,
};

/* ---- mock conversation data (fallback when gateway is not running) -------- */
const MOCK_CHATS = {
  slack: [
    { day: "Today", messages: [
      { from: "bot", sender: "Slack Bot", time: "2:14 PM", text: "New message from #client-michael-thompson:" },
      { from: "me", sender: "You", time: "2:15 PM", text: "Got it, I'll review the appraisal docs and get back to them." },
      { from: "bot", sender: "Slack Bot", time: "2:16 PM", text: "@sarah asked: Are we still on for the closing on the 28th? Title company needs confirmation by EOD Friday." },
      { from: "me", sender: "You", time: "2:20 PM", text: "Yes, confirmed. I'll send the closing disclosure to title today." },
    ]},
  ],
  feishu: [
    { day: "Today", messages: [
      { from: "bot", sender: "飞书 Bot", time: "11:02 AM", text: `Sofia Reyes 在客户群里发了一条消息："上周说的收入证明我已经上传了，麻烦看一下还需要补充什么。"` },
      { from: "me", sender: "You", time: "11:15 AM", text: "收到，我让助理检查一下文档清单。" },
    ]},
  ],
  dingtalk: [
    { day: "Today", messages: [
      { from: "bot", sender: "钉钉 Bot", time: "3:45 PM", text: "Robert Chang 在群里询问：贷款审批进度怎么样了？还需要我做什么吗？" },
      { from: "me", sender: "You", time: "3:50 PM", text: "审批已经到了 underwriting 阶段，目前还差一份房屋保险报价单。" },
    ]},
  ],
};

/* ---- reactive state ------------------------------------------------------ */
const view = ref("list");           // list | config | connecting | convs | chat
const platforms = ref([]);          // loaded from API: { platform, name, desc, fields, configured }
const gatewayStatus = ref(null);    // { running, platforms: { slack: { connected }, ... } }
const conversations = ref([]);      // conversation list for current platform
const activeConvId = ref("");       // selected conversation id
const chatMessages = ref([]);       // formatted messages for current conversation
const activePlatform = ref("");     // key for config or chat view
const fieldValues = ref({});        // { fieldKey: value } during config
const fieldErrors = ref(new Set()); // field keys with red border

/* ---- computed ------------------------------------------------------------ */
const PLATFORMS = computed(() =>
  platforms.value.map(p => ({ ...p, icon: PLATFORM_ICONS[p.platform] || "" }))
);

const connected = computed(() =>
  new Set(platforms.value.filter(p => p.configured).map(p => p.platform))
);

/* ---- helpers ------------------------------------------------------------- */
function platformByKey(key) {
  return PLATFORMS.value.find(p => p.platform === key);
}

/* ---- lifecycle ----------------------------------------------------------- */
onMounted(async () => {
  await loadConnectors();
  // Register global handler for incoming connector messages from backend
  window.__connectorMessages = (msgs) => {
    for (const m of (msgs || [])) {
      if (m.platform === activePlatform.value
          && (!activeConvId.value || m.conv_id === activeConvId.value)
          && view.value === "chat") {
        chatMessages.value.push(formatApiMessage(m));
      }
    }
  };
});

onUnmounted(() => {
  window.__connectorMessages = null;
});

/* ---- API calls ----------------------------------------------------------- */
async function loadConnectors() {
  try {
    const result = await window.readConnectors();
    if (result && !result.error && result.platforms) {
      platforms.value = result.platforms;
    }
  } catch (e) {
    console.warn("readConnectors failed:", e);
  }
  try {
    const status = await window.connectorStatus();
    if (status && !status.error) gatewayStatus.value = status;
  } catch (e) { /* gateway may not be running */ }
}

/* ---- actions ------------------------------------------------------------- */
function onCardClick(key) {
  if (connected.value.has(key)) showConversations(key);
  else showConfig(key);
}

function showConfig(key) {
  activePlatform.value = key;
  fieldValues.value = {};
  fieldErrors.value = new Set();
  view.value = "config";
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

async function showConversations(key) {
  activePlatform.value = key;
  activeConvId.value = "";
  chatMessages.value = [];
  view.value = "convs";
  await loadConversations(key);
}

async function showChat(convId) {
  activeConvId.value = convId;
  view.value = "chat";
  await loadChatHistory(activePlatform.value, convId);
}

function onConvClick(convId) {
  showChat(convId);
}

function backToList() {
  view.value = "list";
  conversations.value = [];
  chatMessages.value = [];
  activeConvId.value = "";
}

function backToConversations() {
  activeConvId.value = "";
  chatMessages.value = [];
  view.value = "convs";
}

async function tryConnect() {
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

  view.value = "connecting";
  try {
    const result = await window.saveConnector(activePlatform.value, fieldValues.value);
    if (result && result.error) {
      console.warn("save_connector:", result.error);
      view.value = "config";
      return;
    }
    // Reload state from backend
    if (result && result.platforms) platforms.value = result.platforms;
    await loadConnectors();
    view.value = "list";
  } catch (e) {
    console.warn("save_connector failed:", e);
    view.value = "config";
  }
}

async function disconnectCurrent() {
  try {
    const result = await window.removeConnector(activePlatform.value);
    if (result && result.platforms) platforms.value = result.platforms;
    await loadConnectors();
  } catch (e) {
    console.warn("remove_connector failed:", e);
  }
  view.value = "list";
}

async function loadConversations(platform) {
  try {
    const result = await window.connectorConversations(platform);
    if (result && !result.error) {
      conversations.value = result;
    }
  } catch (e) {
    console.warn("connectorConversations failed:", e);
  }
}

async function loadChatHistory(platform, convId) {
  try {
    const result = await window.connectorHistory(platform, convId, 50);
    if (result && !result.error) {
      chatMessages.value = (result || []).map(formatApiMessage);
    } else {
      chatMessages.value = [];
    }
  } catch (e) {
    console.warn("connectorHistory failed:", e);
    chatMessages.value = [];
  }
}

function formatApiMessage(m) {
  const ts = m.ts ? new Date(m.ts * 1000) : new Date();
  const timeStr = ts.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  // Inbound (from IM user) → right/green;  Outbound (from bot) → left
  return {
    from: m.direction === "inbound" ? "me" : "bot",
    sender: m.direction === "inbound" ? (m.sender_name || "User") : (m.sender_name || "Bot"),
    time: timeStr,
    text: m.text || "",
    _date: ts,
    images: (m.attachments || []).filter(a => a.is_image && a.data_uri).map(a => ({ src: a.data_uri, name: a.name })),
    files: (m.attachments || []).filter(a => !a.is_image),
  };
}

/* Group messages by day for display (Today / Yesterday / date). */
function groupByDay(msgs) {
  const groups = [];
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
  let current = null;
  for (const m of msgs) {
    const d = m._date || new Date();
    const dayStart = new Date(d); dayStart.setHours(0, 0, 0, 0);
    let label;
    if (dayStart.getTime() === today.getTime()) label = "Today";
    else if (dayStart.getTime() === yesterday.getTime()) label = "Yesterday";
    else label = dayStart.toLocaleDateString([], { month: "short", day: "numeric" });
    if (!current || current.day !== label) {
      current = { day: label, messages: [] };
      groups.push(current);
    }
    current.messages.push(m);
  }
  return groups;
}

function openImage(src) {
  if (!src) return;
  const w = window.open();
  if (w) w.document.write(`<img src="${src}" style="max-width:100%;max-height:100%" />`);
}

// Auto-refresh: reload conversations when returning to convs view.
// (chat history is loaded explicitly by showChat, no need here)
watch(view, async (newView) => {
  if (newView === "convs" && activePlatform.value) {
    await loadConversations(activePlatform.value);
  }
});
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
          v-for="p in PLATFORMS" :key="p.platform"
          class="c-card"
          @click="onCardClick(p.platform)"
        >
          <div class="c-icon" v-html="p.icon"></div>
          <div class="c-body">
            <div class="c-name">{{ p.name }}</div>
            <div class="c-desc">{{ connected.has(p.platform) ? 'Tap to view conversations' : p.desc }}</div>
          </div>
          <div class="c-right">
            <span class="c-status-mini" :class="{ on: connected.has(p.platform) }">
              {{ connected.has(p.platform) ? '● Connected' : 'Not connected' }}
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
                :type="f.secret ? 'password' : 'text'"
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

    <!-- ===== D. Conversation list ===== -->
    <template v-else-if="view === 'convs'">
      <div class="panel-header">
        <div class="panel-header-left">
          <button class="back-btn" @click="backToList">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <div class="c-icon sm" v-html="platformByKey(activePlatform)?.icon"></div>
          <span class="header-title">{{ platformByKey(activePlatform)?.name }}</span>
          <span class="status-tag" :class="{ off: !gatewayStatus?.running }">
            <span class="dot"></span>{{ gatewayStatus?.running ? 'Connected' : 'Offline' }}
          </span>
        </div>
        <button class="action-btn danger" @click="disconnectCurrent">Disconnect</button>
      </div>
      <div class="conv-list">
        <template v-if="conversations.length">
          <div
            v-for="conv in conversations" :key="conv.conv_id"
            class="conv-card"
            @click="onConvClick(conv.conv_id)"
          >
            <div class="conv-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            </div>
            <div class="conv-body">
              <div class="conv-title">{{ conv.conv_id }}</div>
              <div class="conv-meta">{{ conv.message_count }} messages</div>
            </div>
            <div class="conv-right">
              <span class="c-chevron">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </span>
            </div>
          </div>
        </template>
        <div v-else class="chat-empty">
          <div class="chat-empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          </div>
          <div>No conversations yet</div>
          <div class="chat-empty-sub">Messages will appear here when clients reach out via {{ platformByKey(activePlatform)?.name }}</div>
        </div>
      </div>
    </template>

    <!-- ===== E. Chat (read-only) ===== -->
    <template v-else-if="view === 'chat'">
      <div class="panel-header">
        <div class="panel-header-left">
          <button class="back-btn" @click="backToConversations">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <div class="c-icon xs" v-html="platformByKey(activePlatform)?.icon"></div>
          <span class="header-title">{{ platformByKey(activePlatform)?.name }}</span>
          <span class="conv-breadcrumb">{{ activeConvId }}</span>
          <span class="status-tag" :class="{ off: !gatewayStatus?.running }">
            <span class="dot"></span>{{ gatewayStatus?.running ? 'Connected' : 'Offline' }}
          </span>
        </div>
      </div>
      <div class="chat-body">
        <template v-if="groupByDay(chatMessages).length">
          <template v-for="group in groupByDay(chatMessages)" :key="group.day">
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
                <div v-if="m.images && m.images.length" class="cmsg-images">
                  <img
                    v-for="(img, j) in m.images" :key="j"
                    :src="img.src" :alt="img.name || ''"
                    class="cmsg-image"
                    loading="lazy"
                    @click="openImage(img.src)"
                  />
                </div>
                <div v-if="m.text" class="cmsg-bubble">{{ m.text }}</div>
              </div>
            </div>
          </template>
        </template>
        <div v-else class="chat-empty">
          <div class="chat-empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          </div>
          <div>No messages in this conversation</div>
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
.status-tag.off { background: var(--bg-raise); color: var(--text-4); }
.status-tag.off .dot { background: var(--text-4); }
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

/* ---- Conversation list ---- */
.conv-list {
  flex: 1; overflow-y: scroll; padding: 16px 20px;
}
.conv-card {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 14px;
  background: var(--bg-panel); border: 1px solid var(--border);
  margin-bottom: 6px; cursor: pointer;
  transition: border-color .15s, background .15s;
}
.conv-card:hover { border-color: var(--border-soft); background: var(--bg-hover); }
.conv-icon {
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  background: var(--bg-raise); border: 1px solid var(--border-soft);
  flex-shrink: 0;
}
.conv-icon svg { width: 16px; height: 16px; color: var(--text-3); }
.conv-body { flex: 1; min-width: 0; }
.conv-title {
  font: 500 12.5px var(--mono); color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.conv-meta { font: 400 10.5px var(--sans); color: var(--text-4); margin-top: 2px; }
.conv-right { display: flex; align-items: center; flex-shrink: 0; }
.conv-breadcrumb {
  font: 400 10.5px var(--mono); color: var(--text-4);
  max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

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

/* ---- Chat images ---- */
.cmsg-images {
  display: flex; flex-wrap: wrap; gap: 4px;
  margin-bottom: 4px;
}
.cmsg-image {
  max-width: 240px; max-height: 200px;
  object-fit: cover; cursor: pointer;
  border: 1px solid var(--border);
  transition: border-color .15s;
}
.cmsg-image:hover { border-color: var(--brand); }

/* ---- Chat empty state ---- */
.chat-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  color: var(--text-4); font-size: 13px; gap: 6px;
  padding: 40px;
}
.chat-empty-icon { opacity: .25; margin-bottom: 4px; }
.chat-empty-icon svg { width: 24px; height: 24px; }
.chat-empty-sub { font-size: 11px; }
</style>

<!-- Non-scoped: v-html injected SVGs don't carry the data-v attribute,
     so :deep() from the scoped block above can't reliably reach them.
     These rules constrain every SVG inside .connector-* containers. -->
<style>
.connector-msg-avatar svg { width: 16px; height: 16px; display: block; }
.connector-icon svg { display: block; }
</style>
