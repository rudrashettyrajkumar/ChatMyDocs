import { useState } from 'react'
import { useChatStream } from '../hooks/useChatStream'
import { MessageList } from './MessageList'
import { Composer } from './Composer'
import { SourcesDrawer } from './SourcesDrawer'
import { EmptyState } from './EmptyState'

const STARTER_QUESTIONS = [
  'Summarize this document',
  'What are the key takeaways?',
  'Are there any important dates or numbers?',
]

export function Chat({
  hasDocuments,
  onOpenModels,
}: {
  hasDocuments: boolean
  onOpenModels: () => void
}) {
  const { turns, ask, retry } = useChatStream()
  const [drawer, setDrawer] = useState<{ turnId: number; n: number } | null>(null)

  const activeTurn = turns.find((t) => t.id === drawer?.turnId)

  return (
    <div className="relative flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        {turns.length === 0 ? (
          hasDocuments ? (
            <div className="flex h-full flex-col items-center justify-center gap-5 px-6 text-center">
              <div>
                <p className="text-xl font-bold">Ask anything about your documents</p>
                <p className="mt-1.5 text-sm text-foreground-muted">
                  Pick a starter question or type your own below.
                </p>
              </div>
              <div className="flex flex-wrap justify-center gap-2.5">
                {STARTER_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => ask(q)}
                    className="glass rounded-full px-4 py-2 text-sm font-medium transition-all hover:-translate-y-0.5 hover:text-brand"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState />
          )
        ) : (
          <MessageList
            turns={turns}
            onCitationClick={(turnId, n) => setDrawer({ turnId, n })}
            onRetry={retry}
          />
        )}
      </div>

      <Composer onSend={ask} disabled={!hasDocuments} onOpenModels={onOpenModels} />

      <SourcesDrawer
        sources={activeTurn?.sources ?? []}
        activeN={drawer?.n ?? null}
        onClose={() => setDrawer(null)}
      />
    </div>
  )
}
