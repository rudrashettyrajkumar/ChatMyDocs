import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import { Check } from 'lucide-react'
import { Logo } from '../components/ui/Logo'
import { ThemeToggle } from '../components/ui/ThemeToggle'

const PERKS = [
  'Page-cited answers you can actually trust',
  'Your documents, private to your account',
  'Streamed responses — no waiting on a spinner',
]

/** Split layout: a branded, glassy left rail (hidden on mobile) and the form
 *  card on the right. Shared by sign-in and sign-up so they feel like one flow. */
export function AuthScaffold({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}) {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-2">
      {/* Brand rail */}
      <aside className="relative hidden flex-col justify-between overflow-hidden p-12 lg:flex">
        <div className="glass absolute inset-6 -z-10 rounded-3xl" aria-hidden />
        <Link to="/">
          <Logo />
        </Link>
        <div className="max-w-md">
          <h2 className="text-3xl font-extrabold leading-tight">
            Turn any PDF into a <span className="text-gradient">conversation</span>.
          </h2>
          <ul className="mt-8 space-y-4">
            {PERKS.map((perk) => (
              <li key={perk} className="flex items-start gap-3">
                <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-brand-gradient text-white">
                  <Check className="size-3.5" aria-hidden />
                </span>
                <span className="text-foreground-muted">{perk}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="text-sm text-foreground-muted">Built by Raj · FastAPI · Qdrant · RRF · SSE</p>
      </aside>

      {/* Form panel */}
      <main className="flex min-h-dvh flex-col items-center justify-center px-5 py-10">
        <div className="mb-6 flex w-full max-w-md items-center justify-between lg:hidden">
          <Link to="/">
            <Logo />
          </Link>
          <ThemeToggle />
        </div>
        <div className="glass-strong w-full max-w-md animate-fade-up rounded-3xl p-8 sm:p-10">
          <div className="mb-8">
            <h1 className="text-2xl font-extrabold tracking-tight">{title}</h1>
            <p className="mt-1.5 text-foreground-muted">{subtitle}</p>
          </div>
          {children}
          <div className="mt-6 text-center text-sm text-foreground-muted">{footer}</div>
        </div>
        <div className="mt-6 hidden lg:block">
          <ThemeToggle />
        </div>
      </main>
    </div>
  )
}
