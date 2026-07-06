import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import { Loader2 } from 'lucide-react'
import type { Turn } from '../hooks/useChatStream'
import { CitationChip } from './CitationChip'
import { ErrorBanner } from './ErrorBanner'
import { annotateCitations } from '../lib/citations'

type Props = {
  turns: Turn[]
  onCitationClick: (turnId: number, n: number) => void
  onRetry: (turnId: number) => void
}

function markdownComponents(turnId: number, onCitationClick: Props['onCitationClick']): Components {
  return {
    a: ({ href, children }) => {
      if (href?.startsWith('citation:')) {
        const n = Number(href.slice('citation:'.length))
        return <CitationChip n={n} onClick={() => onCitationClick(turnId, n)} />
      }
      return (
        <a href={href} target="_blank" rel="noreferrer" className="underline">
          {children}
        </a>
      )
    },
  }
}

export function MessageList({ turns, onCitationClick, onRetry }: Props) {
  return (
    <div className="flex flex-col gap-6 px-4 py-6">
      {turns.map((turn) => {
        const displayText =
          turn.status === 'streaming' || turn.status === 'reconnecting'
            ? turn.answer
            : annotateCitations(turn.answer, turn.sources)

        return (
          <div key={turn.id} className="flex animate-fade-up flex-col gap-3">
            <div className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-brand-gradient px-4 py-2.5 text-base text-white shadow-glow">
                {turn.question}
              </div>
            </div>

            <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-border bg-surface/50 px-4 py-3 text-base leading-relaxed">
              {turn.answer && (
                <div className="prose prose-sm prose-slate max-w-none dark:prose-invert">
                  <ReactMarkdown components={markdownComponents(turn.id, onCitationClick)}>
                    {displayText}
                  </ReactMarkdown>
                </div>
              )}

              {turn.status === 'streaming' && (
                <span
                  className="ml-0.5 inline-block h-4 w-0.5 animate-blink bg-brand align-middle motion-reduce:animate-none"
                  aria-hidden="true"
                />
              )}

              {turn.status === 'reconnecting' && (
                <div className="mt-2 flex items-center gap-2 text-sm text-foreground-muted">
                  <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                  Reconnecting…
                </div>
              )}

              {(turn.status === 'error' || turn.status === 'rate_limited') && (
                <div className="mt-2">
                  <ErrorBanner
                    message={turn.detail ?? 'Something went wrong.'}
                    onRetry={turn.status === 'error' ? () => onRetry(turn.id) : undefined}
                  />
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
