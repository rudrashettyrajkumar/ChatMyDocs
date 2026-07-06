import { useCallback, useRef, useState } from 'react'
import { uploadDocument } from '../api/client'
import { ApiError } from '../api/types'
import type { DocSummary } from '../api/types'

export type UploadState = {
  file: File
  stage: 'parsing' | 'chunking' | 'embedding' | 'ready' | 'error'
  pct: number
  detail?: string
  doc?: DocSummary
}

let nextId = 0

export function useUpload(onReady: (doc: DocSummary) => void) {
  const [uploads, setUploads] = useState<Record<number, UploadState>>({})
  const controllers = useRef<Record<number, AbortController>>({})

  const patch = (id: number, patch: Partial<UploadState>) =>
    setUploads((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }))

  const dismiss = useCallback((id: number) => {
    setUploads((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
  }, [])

  const startUpload = useCallback(
    async (file: File) => {
      const id = nextId++
      const controller = new AbortController()
      controllers.current[id] = controller
      setUploads((prev) => ({ ...prev, [id]: { file, stage: 'parsing', pct: 0 } }))

      try {
        for await (const event of uploadDocument(file, controller.signal)) {
          if (event.stage === 'parsing') {
            patch(id, { stage: 'parsing', pct: 0 })
          } else if (event.stage === 'chunking') {
            patch(id, { stage: 'chunking', pct: 5 })
          } else if (event.stage === 'embedding') {
            patch(id, { stage: 'embedding', pct: event.pct })
          } else if (event.stage === 'ready') {
            const doc: DocSummary = {
              doc_id: event.doc_id,
              filename: event.filename,
              pages: event.pages,
              chunks: event.chunks,
              uploaded_at: Date.now() / 1000,
            }
            patch(id, { stage: 'ready', pct: 100, doc })
            onReady(doc)
          } else if (event.stage === 'error') {
            patch(id, { stage: 'error', detail: event.detail })
          }
        }
      } catch (err) {
        if (err instanceof ApiError) {
          patch(id, { stage: 'error', detail: err.message })
        } else if (!(err instanceof DOMException && err.name === 'AbortError')) {
          patch(id, { stage: 'error', detail: 'Upload failed. Please try again.' })
        }
      } finally {
        delete controllers.current[id]
      }
    },
    [onReady],
  )

  return { uploads, startUpload, dismiss }
}
