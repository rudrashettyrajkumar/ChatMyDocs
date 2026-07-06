import { Sparkles } from 'lucide-react'
import { Dropzone } from './Dropzone'
import { DocCard } from './DocCard'
import { IngestProgress } from './IngestProgress'
import type { DocSummary } from '../api/types'
import type { UploadState } from '../hooks/useUpload'

const MAX_DOCS_PER_SESSION = 3

type Props = {
  docs: DocSummary[]
  uploads: Record<number, UploadState>
  onFile: (file: File) => void
  onDeleteDoc: (docId: string) => void
  onDismissUpload: (id: number) => void
  onTrySample: () => void
  sampleLoading: boolean
}

export function Sidebar({
  docs,
  uploads,
  onFile,
  onDeleteDoc,
  onDismissUpload,
  onTrySample,
  sampleLoading,
}: Props) {
  const atLimit = docs.length >= MAX_DOCS_PER_SESSION
  const pendingUploads = Object.entries(uploads).filter(([, u]) => u.stage !== 'ready')

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <div>
        <h2 className="mb-3 text-xs font-bold uppercase tracking-wider text-foreground-muted">
          Documents
        </h2>
        <Dropzone onFile={onFile} disabled={atLimit} />
        {atLimit && (
          <p className="mt-2 text-sm text-foreground-muted">
            Limit of {MAX_DOCS_PER_SESSION} documents reached — delete one to add another.
          </p>
        )}
        <button
          onClick={onTrySample}
          disabled={atLimit || sampleLoading}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-border px-3 py-2.5 text-sm font-semibold text-foreground transition-all hover:-translate-y-0.5 hover:border-brand/40 hover:text-brand disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0"
        >
          <Sparkles className="size-4 text-brand" aria-hidden="true" />
          {sampleLoading ? 'Loading sample…' : 'Try a sample PDF'}
        </button>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto">
        {pendingUploads.map(([id, upload]) => (
          <div key={id} className="rounded-lg bg-surface-muted p-3">
            <p className="mb-1.5 truncate text-sm font-medium" title={upload.file.name}>
              {upload.file.name}
            </p>
            <IngestProgress upload={upload} />
            {upload.stage === 'error' && (
              <button
                onClick={() => onDismissUpload(Number(id))}
                className="mt-1.5 text-sm text-foreground-muted underline hover:text-foreground"
              >
                Dismiss
              </button>
            )}
          </div>
        ))}
        {docs.map((doc) => (
          <DocCard key={doc.doc_id} doc={doc} onDelete={() => onDeleteDoc(doc.doc_id)} />
        ))}
      </div>

      <p className="text-sm text-foreground-muted">Documents auto-delete after 24h.</p>
    </div>
  )
}
