import { useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { UploadCloud } from 'lucide-react'

// Mirrors backend/utils/config.py defaults — instant client feedback only;
// the server remains the source of truth and re-validates everything.
const MAX_DOC_MB = 10

type Props = {
  onFile: (file: File) => void
  disabled?: boolean
}

export function Dropzone({ onFile, disabled }: Props) {
  const [dragOver, setDragOver] = useState(false)
  const [hint, setHint] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const validate = (file: File): string | null => {
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      return 'Only PDF files are supported.'
    }
    if (file.size > MAX_DOC_MB * 1024 * 1024) {
      return `File exceeds the ${MAX_DOC_MB}MB limit.`
    }
    return null
  }

  const handleFile = (file: File) => {
    const error = validate(file)
    setHint(error)
    if (!error) onFile(file)
  }

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-disabled={disabled}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (!disabled && (e.key === 'Enter' || e.key === ' ')) inputRef.current?.click()
        }}
        onDragOver={(e) => {
          e.preventDefault()
          if (!disabled) setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={disabled ? undefined : onDrop}
        className={`flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed p-8 text-center transition-colors duration-150 ${
          disabled
            ? 'cursor-not-allowed border-border opacity-40'
            : dragOver
              ? 'border-brand bg-brand/5'
              : 'border-border hover:border-brand/50 hover:bg-brand/5'
        }`}
      >
        <UploadCloud className="size-6 text-brand" aria-hidden="true" />
        <p className="text-sm font-medium">Drag a PDF here, or click to browse</p>
        <p className="text-sm text-foreground-muted">Up to {MAX_DOC_MB}MB</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) handleFile(file)
          e.target.value = ''
        }}
      />
      {hint && <p className="mt-2 text-sm text-destructive">{hint}</p>}
    </div>
  )
}
