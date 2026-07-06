import { Moon, Sun } from 'lucide-react'
import { useTheme } from '../../lib/theme'

export function ThemeToggle() {
  const { theme, toggle } = useTheme()
  const dark = theme === 'dark'
  return (
    <button
      onClick={toggle}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="grid size-10 place-items-center rounded-xl border border-border bg-surface/50 text-foreground-muted transition-colors hover:border-brand/40 hover:text-foreground"
    >
      {dark ? <Sun className="size-5" aria-hidden /> : <Moon className="size-5" aria-hidden />}
    </button>
  )
}
