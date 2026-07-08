// BYOK model configuration — the ONLY home of a user's provider API key.
//
// Keys live in localStorage and ride each request as X-LLM-* / X-Embed-*
// headers (api/client.ts); they are NEVER sent to be stored server-side.
// Demo mode (the default) sends no BYOK headers at all — the backend then
// serves its own env-configured models with the daily demo quotas.
//
// A tiny subscription (custom event) lets the composer chip, the Model
// Studio, and the workspace all re-render on config changes without a
// context provider.

const STORAGE_KEY = 'dc_llm_config_v1'
const CHANGE_EVENT = 'dc-llm-config-changed'

export type LLMConfig = {
  mode: 'demo' | 'byok'
  provider: string
  model: string
  /** Display name of the model, denormalized for the composer chip. */
  modelName: string
  apiKey: string
  /** When true, embeddings also run on the user's key (same provider). */
  byokEmbeddings: boolean
  embedModel: string
}

export const DEMO_CONFIG: LLMConfig = {
  mode: 'demo',
  provider: 'demo',
  model: '',
  modelName: 'Demo mode',
  apiKey: '',
  byokEmbeddings: false,
  embedModel: '',
}

export function loadLLMConfig(): LLMConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEMO_CONFIG
    const parsed = JSON.parse(raw) as Partial<LLMConfig>
    if (parsed.mode !== 'byok' || !parsed.provider || !parsed.apiKey) return DEMO_CONFIG
    return { ...DEMO_CONFIG, ...parsed, mode: 'byok' }
  } catch {
    return DEMO_CONFIG
  }
}

export function saveLLMConfig(config: LLMConfig): void {
  if (config.mode === 'demo') {
    localStorage.removeItem(STORAGE_KEY)
  } else {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
  }
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

export function onLLMConfigChange(listener: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, listener)
  return () => window.removeEventListener(CHANGE_EVENT, listener)
}

/** The BYOK request headers for the current config ({} in demo mode). */
export function byokHeaders(): Record<string, string> {
  const config = loadLLMConfig()
  if (config.mode !== 'byok' || !config.apiKey) return {}
  const headers: Record<string, string> = {
    'X-LLM-Provider': config.provider,
    'X-LLM-Model': config.model,
    'X-LLM-Key': config.apiKey,
  }
  if (config.byokEmbeddings && config.embedModel) {
    headers['X-Embed-Provider'] = config.provider
    headers['X-Embed-Model'] = config.embedModel
    headers['X-Embed-Key'] = config.apiKey
  }
  return headers
}
