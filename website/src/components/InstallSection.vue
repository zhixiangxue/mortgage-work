<template>
  <div>
    <div class="step-list">
      <div class="step">
        <span class="step-num">1</span>
        <div>
          <div class="step-title">下载安装包（仅支持 Windows）</div>
          <div class="step-body">Windows 10 / 11（Windows 11 自带 WebView2 运行时）。下载后解压 zip，双击里面的 MortgageWork.exe 即可运行，免安装。</div>
          <DownloadButton />
        </div>
      </div>
      <div class="step">
        <span class="step-num">2</span>
        <div>
          <div class="step-title">首次启动，自动准备工作区</div>
          <div class="step-body">应用会自动把演示工作仓库克隆到 %USERPROFILE%\MortgageWork\ —— 里面已经预置了 8 个客户档案和 5 家贷款机构的产品文档，不需要自己准备任何数据。</div>
        </div>
      </div>
      <div class="step">
        <span class="step-num">3</span>
        <div>
          <div class="step-title">配置你自己的 LLM（BYOK）</div>
          <div class="step-body">
            打开 Settings → Models，选一个供应商（OpenAI / Anthropic / DeepSeek / 阿里百炼……），填入 API Key 和模型名，点 Check 验证连通。
            密钥只保存在本机 %USERPROFILE%\MortgageWork\settings\settings.yaml，不进工作仓库、不会被同步到任何地方；
            也可以直接用文本编辑器改这个文件，两边是同一份数据：
          </div>
          <pre class="snippet">llm:
  openai:
    api_key: sk-...
    models: [gpt-4o]</pre>
        </div>
      </div>
    </div>
    <p class="setup-note">到这里就完成了。没有数据库要装，没有服务要起 —— 下面直接开始玩。</p>
  </div>
</template>

<script setup>
import DownloadButton from './DownloadButton.vue'
</script>

<style scoped>
.step-list { display: flex; flex-direction: column; }
.step {
  display: flex;
  gap: 18px;
  padding: 22px 0;
  border-bottom: 1px solid var(--border);
}
.step:last-child { border-bottom: 0; }
.step-num {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  font: 700 11px var(--mono);
  color: var(--brand);
  background: var(--tint-green);
  border: 1px solid var(--border-soft);
}
.step-title {
  font: 700 17px var(--sans);
  letter-spacing: -0.01em;
  color: var(--text);
  margin-bottom: 8px;
}
.step-body {
  font-size: 15px;
  line-height: 1.85;
  color: var(--text-2);
  margin-bottom: 14px;
}
.step-body:last-child { margin-bottom: 0; }
.snippet {
  font: 400 12.5px/1.75 var(--mono);
  color: var(--text-2);
  background: var(--bg-panel);
  border: 1px solid var(--border);
  padding: 14px 16px;
  overflow-x: auto;
  margin: 0;
}
/* Reuses the global .dl-btn green button; just shrink it a touch in prose. */
:deep(.dl-btn) { padding: 10px 20px; font-size: 13px; }
.setup-note {
  margin-top: 24px;
  padding-left: 12px;
  border-left: 2px solid var(--brand);
  font-size: 15px;
  line-height: 1.8;
  color: var(--text);
}
</style>
