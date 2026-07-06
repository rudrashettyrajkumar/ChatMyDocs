import { Link } from 'react-router-dom'
import {
  ArrowRight,
  FileText,
  Quote,
  ShieldCheck,
  Sparkles,
  Upload,
  Zap,
} from 'lucide-react'
import { Logo } from '../components/ui/Logo'
import { Button } from '../components/ui/Button'
import { ThemeToggle } from '../components/ui/ThemeToggle'

const FEATURES = [
  {
    icon: Quote,
    title: 'Answers with receipts',
    body: 'Every claim is grounded in your document and tagged with the exact page it came from — click to verify.',
  },
  {
    icon: Zap,
    title: 'Streamed, not stalled',
    body: 'Responses stream token-by-token over SSE with automatic reconnection. No blank spinners.',
  },
  {
    icon: ShieldCheck,
    title: 'Private to your account',
    body: 'Documents are scoped to your login and never leak across users. Delete them anytime.',
  },
]

const STEPS = [
  { icon: Upload, title: 'Upload a PDF', body: 'Drag in a report, contract, or paper — up to 100 pages.' },
  { icon: Sparkles, title: 'Ask anything', body: 'Summaries, key numbers, buried clauses — in plain language.' },
  { icon: FileText, title: 'Trust the answer', body: 'Follow the page citations straight back to the source.' },
]

export function Landing() {
  return (
    <div className="min-h-dvh">
      {/* Nav */}
      <header className="sticky top-0 z-30 px-4 py-3 sm:px-6">
        <nav className="glass mx-auto flex max-w-6xl items-center justify-between rounded-2xl px-4 py-2.5">
          <Logo />
          <div className="flex items-center gap-2 sm:gap-3">
            <ThemeToggle />
            <Link to="/login" className="hidden sm:block">
              <Button variant="ghost" size="sm">
                Sign in
              </Button>
            </Link>
            <Link to="/register">
              <Button size="sm">Get started</Button>
            </Link>
          </div>
        </nav>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-5 pb-16 pt-16 text-center sm:pt-24">
        <span className="glass mx-auto inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium text-foreground-muted">
          <Sparkles className="size-4 text-brand" aria-hidden />
          Chat with your documents — with citations
        </span>
        <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-extrabold leading-[1.1] tracking-tight sm:text-6xl">
          Ask your PDFs anything.
          <br />
          Get answers you can <span className="text-gradient">trust</span>.
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-foreground-muted">
          DocChat turns any PDF into a conversation — streamed, page-cited answers powered by a
          retrieval pipeline built for accuracy, not guesswork.
        </p>
        <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link to="/register" className="w-full sm:w-auto">
            <Button size="lg" className="w-full sm:w-auto">
              Start for free
              <ArrowRight className="size-4" aria-hidden />
            </Button>
          </Link>
          <Link to="/login" className="w-full sm:w-auto">
            <Button variant="secondary" size="lg" className="w-full sm:w-auto">
              Sign in
            </Button>
          </Link>
        </div>

        {/* Floating app preview */}
        <div className="relative mx-auto mt-16 max-w-3xl">
          <div className="glass-strong rounded-3xl p-4 text-left shadow-glow sm:p-6">
            <div className="mb-4 flex items-center gap-1.5">
              <span className="size-3 rounded-full bg-destructive/70" />
              <span className="size-3 rounded-full bg-brand-2/70" />
              <span className="size-3 rounded-full bg-success/70" />
            </div>
            <div className="space-y-4">
              <div className="ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-sm bg-brand-gradient px-4 py-2.5 text-sm text-white">
                What were Q3 revenue and the biggest risk called out?
              </div>
              <div className="max-w-[90%] rounded-2xl rounded-bl-sm border border-border bg-surface/60 px-4 py-3 text-sm">
                Q3 revenue was <strong>$4.2M</strong>, up 18% QoQ
                <sup className="mx-0.5 rounded bg-brand/15 px-1 text-xs font-semibold text-brand">1</sup>.
                The primary risk flagged is supplier concentration
                <sup className="mx-0.5 rounded bg-brand/15 px-1 text-xs font-semibold text-brand">2</sup>.
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-foreground-muted">
                  <span className="rounded-lg border border-border px-2 py-1">📄 report.pdf · p.7</span>
                  <span className="rounded-lg border border-border px-2 py-1">📄 report.pdf · p.14</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-5 py-16">
        <div className="grid gap-5 sm:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="glass rounded-2xl p-6">
              <span className="grid size-11 place-items-center rounded-xl bg-brand-gradient text-white shadow-glow">
                <f.icon className="size-5" aria-hidden />
              </span>
              <h3 className="mt-4 text-lg font-bold">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-foreground-muted">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="mx-auto max-w-6xl px-5 py-16">
        <h2 className="text-center text-3xl font-extrabold tracking-tight">
          Three steps to a smarter document
        </h2>
        <div className="mt-12 grid gap-8 sm:grid-cols-3">
          {STEPS.map((s, i) => (
            <div key={s.title} className="text-center">
              <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-brand-gradient text-white shadow-glow">
                <s.icon className="size-6" aria-hidden />
              </span>
              <p className="mt-4 text-sm font-semibold text-brand">Step {i + 1}</p>
              <h3 className="mt-1 text-lg font-bold">{s.title}</h3>
              <p className="mt-2 text-sm text-foreground-muted">{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-4xl px-5 py-16">
        <div className="glass-strong relative overflow-hidden rounded-3xl p-10 text-center shadow-glow sm:p-14">
          <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
            Ready to talk to your documents?
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-foreground-muted">
            Create a free account and upload your first PDF in under a minute.
          </p>
          <Link to="/register" className="mt-8 inline-block">
            <Button size="lg">
              Get started free
              <ArrowRight className="size-4" aria-hidden />
            </Button>
          </Link>
        </div>
      </section>

      <footer className="mx-auto max-w-6xl px-5 py-10 text-center text-sm text-foreground-muted">
        Built by Raj · FastAPI · Qdrant · RRF · SSE ·{' '}
        <a
          href="https://github.com/rudrashettyrajkumar/ChatMyDocs"
          target="_blank"
          rel="noreferrer"
          className="font-medium text-brand hover:underline"
        >
          Source
        </a>
      </footer>
    </div>
  )
}
