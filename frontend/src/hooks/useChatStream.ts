import { useCallback, useRef, useState } from 'react'
import { streamChat } from '../api/client'
import { ApiError } from '../api/types'
import type { SourceItem } from '../api/types'

export type ChatStatus = 'streaming' | 'reconnecting' | 'done' | 'error' | 'rate_limited'

export type Turn = {
  id: number
  question: string
  answer: string
  sources: SourceItem[]
  status: ChatStatus
  detail?: string
}

const BACKOFF_MS = [1000, 2000, 4000, 8000]
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

let nextTurnId = 0

export function useChatStream() {
  const [turns, setTurns] = useState<Turn[]>([])
  const controllers = useRef<Record<number, AbortController>>({})

  const patch = (id: number, patch: Partial<Turn>) =>
    setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, ...patch } : t)))

  const runTurn = useCallback(async (id: number, question: string, attempt: number) => {
    patch(id, { status: 'streaming', answer: '', sources: [], detail: undefined })
    const controller = new AbortController()
    controllers.current[id] = controller
    let lastSeq = -1

    try {
      let answerBuffer = ''
      for await (const event of streamChat(question, controller.signal)) {
        if (event.type === 'token') {
          if (event.seq > lastSeq) {
            lastSeq = event.seq
            answerBuffer += event.t
            patch(id, { answer: answerBuffer })
          }
        } else if (event.type === 'sources') {
          patch(id, { sources: event.sources })
        } else if (event.type === 'done') {
          patch(id, { status: 'done' })
          return
        } else if (event.type === 'error') {
          patch(id, { status: 'error', detail: event.detail })
          return
        }
      }
    } catch (err) {
      if (err instanceof ApiError) {
        patch(id, {
          status: err.status === 429 ? 'rate_limited' : 'error',
          detail: err.message,
        })
        return
      }
      if (err instanceof DOMException && err.name === 'AbortError') return

      if (attempt < BACKOFF_MS.length) {
        patch(id, { status: 'reconnecting' })
        await sleep(BACKOFF_MS[attempt])
        return runTurn(id, question, attempt + 1)
      }
      patch(id, { status: 'error', detail: 'Connection lost. Please try again.' })
    } finally {
      delete controllers.current[id]
    }
  }, [])

  const ask = useCallback(
    (question: string) => {
      const id = nextTurnId++
      setTurns((prev) => [
        ...prev,
        { id, question, answer: '', sources: [], status: 'streaming' },
      ])
      runTurn(id, question, 0)
    },
    [runTurn],
  )

  const retry = useCallback(
    (id: number) => {
      const turn = turns.find((t) => t.id === id)
      if (turn) runTurn(id, turn.question, 0)
    },
    [turns, runTurn],
  )

  return { turns, ask, retry }
}
