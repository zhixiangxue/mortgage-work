/* Provider catalog behind the Settings dropdowns.

   Not mock data: the ids are chak provider ids, which is exactly what gets
   written into ~/MortgageWork/settings/models.yaml and handed back to chak as
   `provider@base_url:model`. The label is display-only.

   `url` is chak's own default endpoint, shown as the Base URL placeholder so
   the field can stay empty — an empty base_url means "use the provider
   default", which keeps the yaml free of URLs we'd have to maintain. Local
   runtimes have no default, so they carry `needsUrl` and get it prefilled.

   `models` is a shortlist for the picker, not a limit: the Models field takes
   anything typed into it, because a new model ships faster than this file. */
export const CATALOG = [
  { id: "openai",      label: "OpenAI",          url: "https://api.openai.com/v1",
    models: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3"] },
  { id: "anthropic",   label: "Anthropic",       url: "https://api.anthropic.com",
    models: ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"] },
  { id: "google",      label: "Google Gemini",   url: "https://generativelanguage.googleapis.com",
    models: ["gemini-2.5-pro", "gemini-2.5-flash"] },
  { id: "deepseek",    label: "DeepSeek",        url: "https://api.deepseek.com",
    models: ["deepseek-v4-flash", "deepseek-v4-pro"] },
  { id: "bailian",     label: "Alibaba Bailian", url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    models: ["qwen-max", "qwen-plus", "qwen-turbo"] },
  { id: "zhipu",       label: "Zhipu GLM",       url: "https://open.bigmodel.cn/api/paas/v4",
    models: ["glm-4.6", "glm-4-air"] },
  { id: "moonshot",    label: "Moonshot",        url: "https://api.moonshot.cn/v1",
    models: ["kimi-k2-turbo-preview", "moonshot-v1-128k"] },
  { id: "xai",         label: "xAI Grok",        url: "https://api.x.ai/v1",
    models: ["grok-4", "grok-4-fast"] },
  { id: "mistral",     label: "Mistral",         url: "https://api.mistral.ai/v1",
    models: ["mistral-large-latest", "mistral-small-latest"] },
  { id: "siliconflow", label: "SiliconFlow",     url: "https://api.siliconflow.cn/v1",
    models: ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen3-235B-A22B"] },
  { id: "ollama",      label: "Ollama (local)",  url: "http://localhost:11434/v1",
    needsUrl: true, models: ["llama3.3", "qwen3", "gemma3"] },
  { id: "vllm",        label: "vLLM (local)",    url: "http://localhost:8000/v1",
    needsUrl: true, models: [] },
];

export const catalogEntry = id => CATALOG.find(p => p.id === id);

/* Providers we don't ship in the catalog are still legal in the yaml — a
   hand-edited entry must never render as blank. Fall back to its own id. */
export const providerLabel = id => (catalogEntry(id) || { label: id }).label;
