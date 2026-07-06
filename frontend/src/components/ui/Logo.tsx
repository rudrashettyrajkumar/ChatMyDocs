import { MessagesSquare } from 'lucide-react'

/** Wordmark + mark. `size` scales the icon tile; the text is optional so the
 *  same lockup works in a compact topbar and a big auth card. */
export function Logo({ withText = true, className = '' }: { withText?: boolean; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <span className="grid size-9 place-items-center rounded-xl bg-brand-gradient text-white shadow-glow">
        <MessagesSquare className="size-5" aria-hidden />
      </span>
      {withText && (
        <span className="text-lg font-extrabold tracking-tight">
          Doc<span className="text-gradient">Chat</span>
        </span>
      )}
    </span>
  )
}
