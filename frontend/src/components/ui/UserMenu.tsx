import { useEffect, useRef, useState } from 'react'
import { LogOut } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'

function initials(user: { name: string | null; email: string }): string {
  const source = user.name?.trim() || user.email
  return source.slice(0, 2).toUpperCase()
}

export function UserMenu() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  if (!user) return null

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="grid size-10 place-items-center rounded-xl bg-brand-gradient text-sm font-bold text-white shadow-glow transition-transform hover:-translate-y-0.5"
      >
        {initials(user)}
      </button>
      {open && (
        <div
          role="menu"
          className="glass-strong absolute right-0 top-12 z-50 w-60 animate-fade-in rounded-2xl p-2"
        >
          <div className="border-b border-border px-3 py-2.5">
            {user.name && <p className="truncate text-sm font-semibold">{user.name}</p>}
            <p className="truncate text-sm text-foreground-muted">{user.email}</p>
          </div>
          <button
            role="menuitem"
            onClick={logout}
            className="mt-1 flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium text-foreground-muted transition-colors hover:bg-destructive/10 hover:text-destructive"
          >
            <LogOut className="size-4" aria-hidden />
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
