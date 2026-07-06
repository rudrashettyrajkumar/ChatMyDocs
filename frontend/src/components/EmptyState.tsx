import { FileText } from 'lucide-react'

export function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
      <span className="grid size-16 place-items-center rounded-3xl bg-brand-gradient text-white shadow-glow">
        <FileText className="size-7" aria-hidden="true" />
      </span>
      <p className="text-xl font-bold">Upload a document to get started</p>
      <p className="max-w-sm text-sm leading-relaxed text-foreground-muted">
        Drag a PDF into the sidebar, or try the sample document — then ask anything about it and get
        streamed, page-cited answers.
      </p>
    </div>
  )
}
