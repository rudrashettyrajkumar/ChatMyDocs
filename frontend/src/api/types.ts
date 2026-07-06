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

export type HealthStatus = {
  status: 'ok' | 'degraded'
  qdrant: 'ok' | 'down'
  redis: 'ok' | 'down'
  llm: 'ok' | 'down'
}
