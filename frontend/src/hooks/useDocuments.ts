import { useCallback, useEffect, useState } from 'react'
import { deleteDocument, listDocuments } from '../api/client'
import type { DocSummary } from '../api/types'

export function useDocuments() {
  const [docs, setDocs] = useState<DocSummary[]>([])
  const [loaded, setLoaded] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const list = await listDocuments()
      setDocs(list)
    } finally {
      setLoaded(true)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const addDoc = useCallback((doc: DocSummary) => {
    setDocs((prev) => [...prev, doc])
  }, [])

  const removeDoc = useCallback(async (docId: string) => {
    await deleteDocument(docId)
    setDocs((prev) => prev.filter((d) => d.doc_id !== docId))
  }, [])

  return { docs, loaded, refresh, addDoc, removeDoc }
}
