import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import type { SourceItem } from '../api/types'

type Props = {
  sources: SourceItem[]
  activeN: number | null
  onClose: () => void
}

export function SourcesDrawer({ sources, activeN, onClose }: Props) {
  const open = activeN !== null
  const refs = useRef<Record<number, HTMLDivElement | null>>({})

  useEffect(() => {
    if (activeN !== null) {
      refs.current[activeN]?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  }, [activeN])

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/50 transition-opacity duration-300"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <div
        role="dialog"
        aria-label="Sources"
        aria-hidden={!open}
        className={`glass-strong fixed z-50 flex flex-col transition-transform duration-300 ease-out
          inset-x-0 bottom-0 max-h-[80dvh] rounded-t-3xl
          lg:inset-x-auto lg:right-0 lg:top-0 lg:h-full lg:max-h-none lg:w-96 lg:rounded-none lg:rounded-l-3xl
          ${open ? 'translate-y-0 lg:translate-x-0' : 'translate-y-full lg:translate-x-full'} lg:translate-y-0`}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="font-semibold">Sources</h2>
          <button
            onClick={onClose}
            aria-label="Close sources"
            className="flex size-11 items-center justify-center rounded-md text-foreground-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <X className="size-5" aria-hidden="true" />
          </button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {sources.map((source) => (
            <div
              key={source.n}
              ref={(el) => {
                refs.current[source.n] = el
              }}
              className={`rounded-xl border p-3 transition-colors duration-300 ${
                source.n === activeN ? 'border-brand/40 bg-brand/10' : 'border-border'
              } ${source.cited ? '' : 'opacity-50'}`}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <p className="truncate text-sm font-medium" title={source.filename}>
                  [{source.n}] {source.filename} · p.{source.pages}
                </p>
                {!source.cited && (
                  <span className="shrink-0 text-sm text-foreground-muted">not cited</span>
                )}
              </div>
              <p className="text-sm text-foreground-muted">{source.snippet}</p>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
