import { useState } from 'react'
import type { FormEvent } from 'react'
import { Send } from 'lucide-react'
import { ModelChip } from './ui/ModelChip'

type Props = {
  onSend: (question: string) => void
  disabled: boolean
  onOpenModels: () => void
}

export function Composer({ onSend, disabled, onOpenModels }: Props) {
  const [value, setValue] = useState('')

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const question = value.trim()
    if (!question || disabled) return
    onSend(question)
    setValue('')
  }

  return (
    <form onSubmit={submit} className="border-t border-border p-3">
      <div className="mb-2 flex items-center justify-between px-1">
        <ModelChip onClick={onOpenModels} />
        <span className="hidden text-[11px] text-foreground-muted sm:block">
          Answers are grounded in your documents with page citations
        </span>
      </div>
      <div className="glass-strong flex items-center gap-2 rounded-2xl p-1.5">
        <div className="group relative flex-1">
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={disabled}
            placeholder={disabled ? 'Upload a document to start chatting' : 'Ask about your documents…'}
            className="min-h-[44px] w-full rounded-xl bg-transparent px-4 py-2 text-base placeholder:text-foreground-muted focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-60"
          />
          {disabled && (
            <span className="pointer-events-none absolute -top-10 left-0 hidden rounded-md bg-surface-muted px-2 py-1 text-sm text-foreground-muted shadow-soft group-hover:block">
              Upload a document first
            </span>
          )}
        </div>
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          aria-label="Send"
          className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand-gradient text-white shadow-glow transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
        >
          <Send className="size-4" aria-hidden="true" />
        </button>
      </div>
    </form>
  )
}
