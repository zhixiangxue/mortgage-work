/* Curated provider/model catalog backing the Add Model dropdowns (demo data).
   Single source of truth: docs.js renders the initial menus from it, bridge.js
   re-renders the model menu when the provider changes. */
export const MODEL_CATALOG = {
  OpenAI:    { url: "https://api.openai.com/v1", models: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3"] },
  Anthropic: { url: "https://api.anthropic.com", models: ["claude-sonnet", "claude-opus", "claude-haiku"] },
  DeepSeek:  { url: "https://api.deepseek.com", models: ["deepseek-chat", "deepseek-reasoner"] },
  Google:    { url: "https://generativelanguage.googleapis.com", models: ["gemini-2.5-pro", "gemini-2.5-flash"] },
  xAI:       { url: "https://api.x.ai/v1", models: ["grok-4", "grok-4-fast"] },
  Ollama:    { url: "http://localhost:11434", models: ["llama3.3", "qwen3", "gemma3"] },
};

export const PROVIDERS = Object.keys(MODEL_CATALOG);

export const providerItemsHtml = () =>
  PROVIDERS.map(p => `<div class="dd-item" onclick="pickProvider(this)">${p}</div>`).join("");

/* Model menu is multi-select: clicking toggles .sel, first model pre-selected */
export const modelItemsHtml = prov =>
  MODEL_CATALOG[prov].models.map((m, i) =>
    `<div class="dd-item${i === 0 ? " sel" : ""}" onclick="pickModel(this, event)">${m}</div>`).join("");
