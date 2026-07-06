import { FileText, Trash2 } from 'lucide-react'
import type { DocSummary } from '../api/types'

type Props = {
  doc: DocSummary
  onDelete: () => void
}

export function DocCard({ doc, onDelete }: Props) {
  return (
    <div className="flex items-center gap-2.5 rounded-xl border border-border bg-surface-muted/60 p-3 transition-colors hover:border-brand/30">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-brand/10 text-brand">
        <FileText className="size-4" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium" title={doc.filename}>
          {doc.filename}
        </p>
        <p className="text-sm text-foreground-muted">
          {doc.pages} pages · {doc.chunks} chunks
        </p>
      </div>
      <button
        onClick={onDelete}
        aria-label={`Delete ${doc.filename}`}
        className="flex size-11 shrink-0 items-center justify-center rounded-md text-foreground-muted hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface-muted"
      >
        <Trash2 className="size-4" aria-hidden="true" />
      </button>
    </div>
  )
}
