<template>
  <section id="models" class="models">
    <div class="shell">
      <div class="section-head">
        <p class="section-eyebrow"><span class="dot"></span> Bring your own model</p>
        <h2>Your models. Your rules.</h2>
        <p>
          Works with virtually every LLM provider — from OpenAI and Anthropic to
          DeepSeek, Qwen, and local models. Your keys stay on your machine.
        </p>
      </div>
    </div>

    <!-- Marquee ticker: two rows, opposite directions, monochrome -->
    <div class="model-ticker">
      <div class="ticker-row">
        <div class="ticker-track">
          <span v-for="(m, i) in row1" :key="'a'+i" class="ticker-item">
            <span class="ti-name">{{ m.name }}</span>
            <span class="ti-prov">{{ m.provider }}</span>
          </span>
          <span v-for="(m, i) in row1" :key="'b'+i" class="ticker-item" aria-hidden="true">
            <span class="ti-name">{{ m.name }}</span>
            <span class="ti-prov">{{ m.provider }}</span>
          </span>
        </div>
      </div>
      <div class="ticker-row reverse">
        <div class="ticker-track">
          <span v-for="(m, i) in row2" :key="'c'+i" class="ticker-item">
            <span class="ti-name">{{ m.name }}</span>
            <span class="ti-prov">{{ m.provider }}</span>
          </span>
          <span v-for="(m, i) in row2" :key="'d'+i" class="ticker-item" aria-hidden="true">
            <span class="ti-name">{{ m.name }}</span>
            <span class="ti-prov">{{ m.provider }}</span>
          </span>
        </div>
      </div>
    </div>

    <div class="shell">
      <div class="model-footnote">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/>
        </svg>
        <span>Works with any OpenAI or Anthropic compatible API out of the box</span>
      </div>
    </div>
  </section>
</template>

<script setup>
// Real model names sourced from OpenRouter / token.app
const row1 = [
  { name: 'GPT-5.6 Terra Pro',  provider: 'OpenAI' },
  { name: 'GPT-5.6 Luna',       provider: 'OpenAI' },
  { name: 'Claude Opus 5',      provider: 'Anthropic' },
  { name: 'Claude Sonnet 5',    provider: 'Anthropic' },
  { name: 'Gemini 3.5 Flash',   provider: 'Google' },
  { name: 'Gemini 3.1 Pro',     provider: 'Google' },
  { name: 'DeepSeek V4 Pro',    provider: 'DeepSeek' },
  { name: 'DeepSeek V4 Flash',  provider: 'DeepSeek' },
  { name: 'Grok 4.5',           provider: 'xAI' },
  { name: 'Grok 4.3',           provider: 'xAI' },
  { name: 'Qwen3.7 Max',        provider: 'Alibaba' },
  { name: 'Qwen3.6 Plus',       provider: 'Alibaba' },
  { name: 'GLM-5.2',            provider: 'Zhipu' },
  { name: 'Kimi K3',            provider: 'Moonshot' },
  { name: 'Llama 4 Maverick',   provider: 'Meta' },
  { name: 'Mistral Large 2512', provider: 'Mistral' },
  { name: 'Phi-4',              provider: 'Microsoft' },
  { name: 'Seed 2.0',           provider: 'ByteDance' },
]

const row2 = [
  { name: 'Claude Opus 4.8',      provider: 'Anthropic' },
  { name: 'Claude Haiku 4.5',     provider: 'Anthropic' },
  { name: 'GPT-5.6 Luna Pro',     provider: 'OpenAI' },
  { name: 'Gemini 3.6 Flash',     provider: 'Google' },
  { name: 'Gemma 4 31B',          provider: 'Google' },
  { name: 'Command A',            provider: 'Cohere' },
  { name: 'MiniMax M3',           provider: 'MiniMax' },
  { name: 'Ernie 4.5 VL',         provider: 'Baidu' },
  { name: 'Hunyuan A13B',         provider: 'Tencent' },
  { name: 'Solar Pro 3',          provider: 'Upstage' },
  { name: 'Nova Premier',         provider: 'Amazon' },
  { name: 'Qwen3.8 Max',          provider: 'Alibaba' },
  { name: 'Qwen3 Coder',          provider: 'Alibaba' },
  { name: 'GLM-5',                provider: 'Zhipu' },
  { name: 'Llama 4 Scout',        provider: 'Meta' },
  { name: 'Kimi K2.7 Code',       provider: 'Moonshot' },
  { name: 'Mistral Medium 3.5',   provider: 'Mistral' },
  { name: 'MiMo V2.5 Pro',        provider: 'Xiaomi' },
]
</script>
