import { getToken, handleUnauthorized } from '../lib/auth-token'
import type { ApiErrorBody, ChatEvent, DocSummary, HealthStatus, IngestProgressEvent } from './types'
import { ApiError } from './types'

const API_URL = import.meta.env.VITE_API_URL as string

function authHeaders(): HeadersInit {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function throwIfError(res: Response): Promise<void> {
  if (res.ok) return
  // A 401 means the token is gone/expired — log out globally, then surface it.
  if (res.status === 401) handleUnauthorized()
  let body: ApiErrorBody
  try {
    body = await res.json()
  } catch {
    body = { error: 'unknown', detail: `Request failed (${res.status})` }
  }
  throw new ApiError(body, res.status)
}

/** Parses a `text/event-stream` body into `{event, data}` frames.
 * Comment lines (heartbeats, `: ping`) are swallowed here — callers never see them. */
async function* parseSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<{ event: string; data: unknown }> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) return
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''
      for (const frame of frames) {
        if (!frame || frame.startsWith(':')) continue
        let eventName = 'message'
        let data: unknown = null
        for (const line of frame.split('\n')) {
          if (line.startsWith('event: ')) eventName = line.slice(7)
          else if (line.startsWith('data: ')) data = JSON.parse(line.slice(6))
        }
        if (data !== null) yield { event: eventName, data }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function checkHealth(): Promise<HealthStatus> {
  const res = await fetch(`${API_URL}/health`)
  return res.json()
}

export async function listDocuments(): Promise<DocSummary[]> {
  const res = await fetch(`${API_URL}/documents`, { headers: authHeaders() })
  await throwIfError(res)
  return res.json()
}

export async function deleteDocument(docId: string): Promise<void> {
  const res = await fetch(`${API_URL}/documents/${docId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  await throwIfError(res)
}

export async function* uploadDocument(
  file: File,
  signal?: AbortSignal,
): AsyncGenerator<IngestProgressEvent> {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch(`${API_URL}/documents`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
    signal,
  })
  await throwIfError(res)
  if (!res.body) return

  for await (const frame of parseSSE(res.body)) {
    yield frame.data as IngestProgressEvent
  }
}

export async function* streamChat(question: string, signal?: AbortSignal): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_URL}/chat/stream`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
    signal,
  })
  await throwIfError(res)
  if (!res.body) return

  for await (const frame of parseSSE(res.body)) {
    yield { type: frame.event, ...(frame.data as object) } as ChatEvent
  }
}

export async function fetchSamplePdf(): Promise<File> {
  const res = await fetch('/sample.pdf')
  const blob = await res.blob()
  return new File([blob], 'sample.pdf', { type: 'application/pdf' })
}
