import { useState } from 'react'
import { FileText, Loader2 } from 'lucide-react'
import { Sidebar } from '../components/Sidebar'
import { Chat } from '../components/Chat'
import { ErrorBanner } from '../components/ErrorBanner'
import { MobileSidebarSheet } from '../components/MobileSidebarSheet'
import { Logo } from '../components/ui/Logo'
import { ThemeToggle } from '../components/ui/ThemeToggle'
import { UserMenu } from '../components/ui/UserMenu'
import { useDocuments } from '../hooks/useDocuments'
import { useUpload } from '../hooks/useUpload'
import { useHealth } from '../hooks/useHealth'
import { fetchSamplePdf } from '../api/client'

const HEALTH_DOT: Record<string, string> = {
  ok: 'bg-success',
  degraded: 'bg-brand-2',
  unreachable: 'bg-destructive',
  checking: 'bg-foreground-muted',
}

export function Workspace() {
  const { state: healthState, recheck } = useHealth()
  const { docs, addDoc, removeDoc } = useDocuments()
  const { uploads, startUpload, dismiss } = useUpload(addDoc)
  const [sampleLoading, setSampleLoading] = useState(false)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  const handleTrySample = async () => {
    setSampleLoading(true)
    try {
      const file = await fetchSamplePdf()
      await startUpload(file)
    } finally {
      setSampleLoading(false)
    }
  }

  const uploading = Object.values(uploads).some((u) => u.stage !== 'ready' && u.stage !== 'error')

  const sidebarProps = {
    docs,
    uploads,
    onFile: startUpload,
    onDeleteDoc: removeDoc,
    onDismissUpload: dismiss,
    onTrySample: handleTrySample,
    sampleLoading,
  }

  return (
    <div className="flex h-dvh flex-col">
      {/* Topbar */}
      <header className="z-20 px-3 pt-3">
        <div className="glass flex items-center justify-between rounded-2xl px-4 py-2.5">
          <Logo />
          <div className="flex items-center gap-2 sm:gap-3">
            <span
              className="hidden items-center gap-2 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground-muted sm:flex"
              title={`Backend: ${healthState}`}
            >
              <span className={`size-2 rounded-full ${HEALTH_DOT[healthState]}`} aria-hidden />
              {healthState === 'ok' ? 'All systems go' : healthState}
            </span>
            <ThemeToggle />
            <UserMenu />
          </div>
        </div>
      </header>

      {healthState === 'unreachable' && (
        <div className="px-3 pt-3">
          <ErrorBanner
            message="Can't reach the backend right now — it may be waking up. Try again in a moment."
            onRetry={recheck}
          />
        </div>
      )}
      {healthState === 'degraded' && (
        <div className="px-3 pt-3">
          <ErrorBanner message="Some services are degraded — answers may be slower than usual." />
        </div>
      )}

      <div className="flex flex-1 overflow-hidden p-3 lg:grid lg:grid-cols-[20rem_1fr] lg:gap-3">
        <aside className="hidden lg:flex lg:flex-col lg:overflow-hidden">
          <div className="glass flex-1 overflow-hidden rounded-2xl">
            <Sidebar {...sidebarProps} />
          </div>
        </aside>

        <div className="glass flex flex-1 flex-col overflow-hidden rounded-2xl">
          <div className="flex items-center justify-between border-b border-border p-3 lg:hidden">
            <span className="font-semibold">Chat</span>
            <button
              onClick={() => setMobileSidebarOpen(true)}
              className="flex items-center gap-2 rounded-full border border-border px-3 py-1.5 text-sm font-medium hover:border-brand/40"
            >
              <FileText className="size-4" aria-hidden />
              Documents ({docs.length})
              {uploading && <Loader2 className="size-3.5 animate-spin" aria-hidden />}
            </button>
          </div>

          <div className="flex-1 overflow-hidden">
            <Chat hasDocuments={docs.length > 0} />
          </div>
        </div>
      </div>

      <MobileSidebarSheet open={mobileSidebarOpen} onClose={() => setMobileSidebarOpen(false)}>
        <Sidebar {...sidebarProps} />
      </MobileSidebarSheet>
    </div>
  )
}
