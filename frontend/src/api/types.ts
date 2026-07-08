export type AuthUser = {
  id: string
  email: string
  name: string | null
  created_at: number
}

export type AuthResponse = {
  access_token: string
  user: AuthUser
}

export type DocSummary = {
  doc_id: string
  filename: string
  pages: number
  chunks: number
  uploaded_at: number
}

export type IngestProgressEvent =
  | { stage: 'parsing' }
  | { stage: 'chunking'; chunks: number }
  | { stage: 'embedding'; pct: number }
  | { stage: 'ready'; doc_id: string; filename: string; pages: number; chunks: number }
  | { stage: 'error'; detail: string }

export type SourceItem = {
  n: number
  doc_id: string
  filename: string
  pages: string
  snippet: string
  score: number
  cited: boolean
}

export type ChatEvent =
  | { type: 'token'; seq: number; t: string }
  | { type: 'sources'; sources: SourceItem[] }
  | { type: 'done' }
  | { type: 'error'; detail: string }

/** The `{error, detail}` body shared by every pre-stream 4xx rejection (documents.py, rate_limit.py). */
export type ApiErrorBody = {
  error: string
  detail: string
}

export class ApiError extends Error {
  code: string
  status: number
  constructor(body: ApiErrorBody, status: number) {
    super(body.detail)
    this.code = body.error
    this.status = status
  }
}

// --- BYOK model catalog (GET /api/models) ---------------------------------

export type CatalogModel = {
  id: string
  name: string
  accuracy: number // 1-5 editorial tier
  speed: 'blazing' | 'fast' | 'balanced' | 'deliberate'
  cost: string
  context: string
  free: boolean
  recommended: boolean
  notes: string
}

export type CatalogProvider = {
  id: string
  name: string
  tagline: string
  kind: 'free' | 'freemium' | 'paid'
  key_url: string
  key_steps: string[]
  models: CatalogModel[]
  embedding_models: CatalogModel[]
  allows_custom_model: boolean
}

export type ModelsCatalog = {
  providers: CatalogProvider[]
  embed_providers: string[]
  demo_available: boolean
  embedding_pin: string | null
}

export type ValidateResult = {
  ok: boolean
  detail: string
  latency_ms?: number
}

export type HealthStatus = {
  status: 'ok' | 'degraded'
  qdrant: 'ok' | 'down'
  redis: 'ok' | 'down'
  llm: 'ok' | 'down'
}
