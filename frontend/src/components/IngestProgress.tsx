import { Loader2 } from 'lucide-react'
import type { UploadState } from '../hooks/useUpload'

const STAGE_LABEL: Record<UploadState['stage'], string> = {
  parsing: 'Parsing PDF…',
  chunking: 'Splitting into chunks…',
  embedding: 'Embedding…',
  ready: 'Ready',
  error: 'Failed',
}

export function IngestProgress({ upload }: { upload: UploadState }) {
  if (upload.stage === 'error') {
    return <p className="text-sm text-destructive">{upload.detail}</p>
  }
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-sm text-foreground-muted">
        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
        <span>{STAGE_LABEL[upload.stage]}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-border">
        <div
          className="h-full rounded-full bg-brand-gradient transition-[width] duration-300 ease-out"
          style={{ width: `${upload.pct}%` }}
        />
      </div>
    </div>
  )
}
