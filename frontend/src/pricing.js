/* Shared pricing helpers — the single source of truth for turning usage
   metadata into model identities and USD costs. Both the conversation
   inspector (per-conversation) and the usage panel (per day × model) cost
   through these functions, so the two surfaces can never disagree.

   Price table shape (model_prices.json):
     { models: { "<provider>/<model>": { input, output, cache_write?, cache_read? } },
       aliases: { "<alias>": "<provider>/<model>" } }
   All prices are per 1M tokens. */

export function modelUri(meta = {}) {
  const pt = meta.provider_trace || {};
  const direct = meta.model_uri || meta.model_ref || meta.model_name || meta.model;
  const p = pt.resolved_provider || pt.provider || meta.provider;
  const m = pt.resolved_model || pt.model || direct;
  if (p && m && !String(m).includes("/")) return `${p}/${m}`;
  return m || p || null;
}

export function normalizeModelKey(s) {
  return String(s || "")
    .trim()
    .toLowerCase()
    .replace(/^model:\/\//, "")
    .replace(/[?#].*$/, "")
    .replace(/:.+$/, "")
    .replace(/^models\//, "");
}

/* Map an observed model uri onto a model_prices.json key. Tries exact match,
   aliases, case-insensitive match, then versioned-id prefix matching
   (openai/gpt-4o-2024-08-06 -> openai/gpt-4o). Null when unpriced. */
export function canonicalPriceKey(uri, prices = {}) {
  if (!uri) return null;
  const models = prices.models || {}, aliases = prices.aliases || {};
  const modelKeys = Object.keys(models);
  const aliasKeys = Object.keys(aliases);
  const candidates = [];
  const raw = String(uri || "").trim();
  const providerColon = raw.match(/^(openai|anthropic|google|deepseek|moonshot|xai):(.+)$/i);
  const rawProvider = providerColon ? `${providerColon[1].toLowerCase()}/${providerColon[2]}` : raw;
  const norm = normalizeModelKey(rawProvider);
  candidates.push(raw, rawProvider, norm, norm.split("/").pop());
  for (const c of [...candidates]) {
    if (!c) continue;
    if (models[c]) return c;
    if (aliases[c] && models[aliases[c]]) return aliases[c];
  }
  const lowerModel = new Map(modelKeys.map(k => [normalizeModelKey(k), k]));
  const lowerAlias = new Map(aliasKeys.map(k => [normalizeModelKey(k), aliases[k]]));
  for (const c of candidates.map(normalizeModelKey)) {
    if (lowerModel.has(c)) return lowerModel.get(c);
    if (lowerAlias.has(c) && models[lowerAlias.get(c)]) return lowerAlias.get(c);
  }
  // Versioned model ids: openai/gpt-4o-2024-08-06 -> openai/gpt-4o.
  const prefix = modelKeys
    .slice()
    .sort((a, b) => b.length - a.length)
    .find(k => norm === normalizeModelKey(k) || norm.startsWith(normalizeModelKey(k) + "-"));
  if (prefix) return prefix;
  const model = norm.split("/").pop();
  const aliasPrefix = aliasKeys
    .slice()
    .sort((a, b) => b.length - a.length)
    .find(k => model === normalizeModelKey(k) || model.startsWith(normalizeModelKey(k) + "-"));
  return aliasPrefix && models[aliases[aliasPrefix]] ? aliases[aliasPrefix] : null;
}

/* USD cost for one aggregated bucket { prompt, completion, cacheW, cacheR }.
   Cache token prices fall back to the input price when the table has no
   dedicated entry. Returns { known, cost, key }. */
export function costFor(bucket, prices) {
  const key = canonicalPriceKey(bucket.uri, prices || {});
  const p = key && prices?.models ? prices.models[key] : null;
  if (!p) return { known: false, cost: NaN, key: null };
  const cost = (
    bucket.prompt * (p.input || 0) +
    bucket.completion * (p.output || 0) +
    bucket.cacheW * (p.cache_write ?? p.input ?? 0) +
    bucket.cacheR * (p.cache_read ?? p.input ?? 0)
  ) / 1_000_000;
  return { known: true, cost, key };
}
