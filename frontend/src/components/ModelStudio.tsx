import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  ArrowUpRight,
  Brain,
  Check,
  CheckCircle2,
  ChevronDown,
  Eye,
  EyeOff,
  Gauge,
  Gem,
  KeyRound,
  Loader2,
  Route,
  ShieldCheck,
  Sparkles,
  Wand2,
  X,
  XCircle,
  Zap,
} from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { fetchModelCatalog, validateProviderKey } from '../api/client'
import type { CatalogModel, CatalogProvider, ModelsCatalog } from '../api/types'
import { DEMO_CONFIG, loadLLMConfig, saveLLMConfig } from '../lib/llmConfig'
import type { LLMConfig } from '../lib/llmConfig'

// Per-provider visual identity (icon + gradient), keyed by catalog id.
const PROVIDER_LOOK: Record<string, { icon: typeof Zap; gradient: string }> = {
  groq: { icon: Zap, gradient: 'from-amber-400 to-orange-500' },
  openrouter: { icon: Route, gradient: 'from-indigo-400 to-violet-500' },
  openai: { icon: Sparkles, gradient: 'from-emerald-400 to-teal-500' },
  anthropic: { icon: Brain, gradient: 'from-orange-400 to-rose-500' },
  gemini: { icon: Gem, gradient: 'from-sky-400 to-cyan-500' },
}

const KIND_BADGE: Record<CatalogProvider['kind'], { label: string; cls: string }> = {
  free: { label: '100% FREE', cls: 'bg-success/15 text-success' },
  freemium: { label: 'FREE TIER', cls: 'bg-brand/15 text-brand' },
  paid: { label: 'PAID KEY', cls: 'bg-foreground-muted/15 text-foreground-muted' },
}

const ACCURACY_LABEL = ['', 'Basic', 'Good', 'Great', 'Excellent', 'Frontier']
const SPEED_LABEL: Record<CatalogModel['speed'], string> = {
  blazing: 'Blazing',
  fast: 'Fast',
  balanced: 'Balanced',
  deliberate: 'Deliberate',
}

type ValidationState =
  | { status: 'idle' }
  | { status: 'checking' }
  | { status: 'ok'; detail: string }
  | { status: 'error'; detail: string }

/** 5-segment accuracy meter — color + width + text label (never color alone). */
function AccuracyMeter({ tier }: { tier: number }) {
  return (
    <div className="flex items-center gap-2" title={`Accuracy: ${ACCURACY_LABEL[tier]} (${tier}/5)`}>
      <div className="flex gap-0.5" role="img" aria-label={`Accuracy ${tier} out of 5`}>
        {[1, 2, 3, 4, 5].map((i) => (
          <span
            key={i}
            className={`h-1.5 w-3 rounded-full ${
              i <= tier ? 'bg-gradient-to-r from-brand to-brand-2' : 'bg-foreground-muted/20'
            }`}
          />
        ))}
      </div>
      <span className="text-[11px] font-semibold text-foreground-muted">{ACCURACY_LABEL[tier]}</span>
    </div>
  )
}

function ModelCard({
  model,
  selected,
  onSelect,
}: {
  model: CatalogModel
  selected: boolean
  onSelect: () => void
}) {
  const reduce = useReducedMotion()
  return (
    <motion.button
      type="button"
      onClick={onSelect}
      whileHover={reduce ? undefined : { y: -2 }}
      whileTap={reduce ? undefined : { scale: 0.98 }}
      aria-pressed={selected}
      className={`glass w-full cursor-pointer rounded-2xl p-3.5 text-left transition-colors ${
        selected ? 'ring-2 ring-brand' : 'hover:border-brand/40'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-bold">{model.name}</p>
          <p className="mt-0.5 truncate text-[11px] text-foreground-muted">{model.id}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {model.recommended && (
            <span className="rounded-full bg-brand-2/15 px-2 py-0.5 text-[10px] font-bold text-brand-2">
              PICK
            </span>
          )}
          {model.free && (
            <span className="rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-bold text-success">
              FREE
            </span>
          )}
          {selected && <Check className="size-4 text-brand" aria-hidden />}
        </div>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <AccuracyMeter tier={model.accuracy} />
        <span className="flex items-center gap-1 text-[11px] font-medium text-foreground-muted">
          <Gauge className="size-3" aria-hidden />
          {SPEED_LABEL[model.speed]}
        </span>
        <span className="text-[11px] font-medium text-foreground-muted">{model.context} ctx</span>
        <span className="text-[11px] font-medium text-foreground-muted">{model.cost}</span>
      </div>
      {model.notes && <p className="mt-2 text-[11px] leading-snug text-foreground-muted">{model.notes}</p>}
    </motion.button>
  )
}

function KeySteps({ provider }: { provider: CatalogProvider }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-2xl border border-border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex min-h-[44px] w-full cursor-pointer items-center justify-between gap-2 px-3.5 py-2.5 text-sm font-semibold"
      >
        <span className="flex items-center gap-2">
          <KeyRound className="size-4 text-brand" aria-hidden />
          How to get your {provider.name} key
          {provider.kind !== 'paid' && (
            <span className="rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-bold text-success">
              FREE
            </span>
          )}
        </span>
        <ChevronDown className={`size-4 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <ol className="space-y-2 px-3.5 pb-3">
              {provider.key_steps.map((step, i) => (
                <li key={i} className="flex gap-2.5 text-[13px] leading-snug text-foreground-muted">
                  <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[11px] font-bold text-brand">
                    {i + 1}
                  </span>
                  {step}
                </li>
              ))}
              <a
                href={provider.key_url}
                target="_blank"
                rel="noreferrer"
                className="ml-7 inline-flex min-h-[36px] items-center gap-1 text-[13px] font-semibold text-brand hover:underline"
              >
                Open {provider.key_url.replace('https://', '').split('/')[0]}
                <ArrowUpRight className="size-3.5" aria-hidden />
              </a>
            </ol>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

type Props = {
  open: boolean
  onClose: () => void
}

export function ModelStudio({ open, onClose }: Props) {
  const reduce = useReducedMotion()
  const [catalog, setCatalog] = useState<ModelsCatalog | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [draft, setDraft] = useState<LLMConfig>(loadLLMConfig)
  const [showKey, setShowKey] = useState(false)
  const [customModel, setCustomModel] = useState('')
  const [validation, setValidation] = useState<ValidationState>({ status: 'idle' })

  useEffect(() => {
    if (!open) return
    setDraft(loadLLMConfig())
    setValidation({ status: 'idle' })
    fetchModelCatalog()
      .then((data) => {
        setCatalog(data)
        setCatalogError(null)
      })
      .catch(() => setCatalogError("Couldn't load the model catalog. Close and try again."))
  }, [open])

  // Close on Escape (modal escape route).
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const provider = useMemo(
    () => catalog?.providers.find((p) => p.id === draft.provider) ?? null,
    [catalog, draft.provider],
  )

  const pickProvider = (p: CatalogProvider) => {
    const recommended = p.models.find((m) => m.recommended) ?? p.models[0]
    const embed = p.embedding_models.find((m) => m.recommended) ?? p.embedding_models[0]
    setValidation({ status: 'idle' })
    setCustomModel('')
    setDraft((d) => ({
      ...d,
      mode: 'byok',
      provider: p.id,
      model: recommended.id,
      modelName: recommended.name,
      byokEmbeddings: d.byokEmbeddings && p.embedding_models.length > 0,
      embedModel: embed?.id ?? '',
      apiKey: d.provider === p.id ? d.apiKey : '',
    }))
  }

  const pickModel = (m: CatalogModel) => {
    setCustomModel('')
    setDraft((d) => ({ ...d, model: m.id, modelName: m.name }))
  }

  const applyCustomModel = (value: string) => {
    setCustomModel(value)
    const id = value.trim()
    if (id) setDraft((d) => ({ ...d, model: id, modelName: id }))
  }

  const validate = async () => {
    if (!provider || !draft.apiKey) return
    setValidation({ status: 'checking' })
    try {
      const result = await validateProviderKey({
        provider: draft.provider,
        model: draft.model,
        api_key: draft.apiKey,
        kind: 'chat',
      })
      setValidation(result.ok ? { status: 'ok', detail: result.detail } : { status: 'error', detail: result.detail })
    } catch {
      setValidation({ status: 'error', detail: "Couldn't reach the server to test the key." })
    }
  }

  const saveDemo = () => {
    saveLLMConfig(DEMO_CONFIG)
    onClose()
  }

  const saveByok = () => {
    saveLLMConfig({ ...draft, mode: 'byok' })
    onClose()
  }

  const canSave = draft.provider !== 'demo' && draft.apiKey.trim().length > 0 && draft.model.trim().length > 0
  const pinMismatch =
    catalog?.embedding_pin &&
    draft.byokEmbeddings &&
    catalog.embedding_pin !== `${draft.provider}/${draft.embedModel}`

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 backdrop-blur-sm sm:items-center sm:p-6"
          onClick={onClose}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Model Studio — choose your AI model"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 32, scale: 0.97 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: 24, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 380, damping: 32 }}
            onClick={(e) => e.stopPropagation()}
            className="glass-strong flex max-h-[92dvh] w-full max-w-3xl flex-col overflow-hidden rounded-t-3xl sm:rounded-3xl"
          >
            {/* Header */}
            <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
              <div className="flex items-center gap-3">
                <span className="flex size-10 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-glow">
                  <Wand2 className="size-5" aria-hidden />
                </span>
                <div>
                  <h2 className="text-base font-extrabold">Model Studio</h2>
                  <p className="text-xs text-foreground-muted">
                    Bring your own key — chat with any model, on your quota.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="flex size-10 cursor-pointer items-center justify-center rounded-xl text-foreground-muted transition-colors hover:bg-surface-muted hover:text-foreground"
              >
                <X className="size-5" aria-hidden />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
              {catalogError && (
                <p className="rounded-2xl bg-destructive/10 px-4 py-3 text-sm font-medium text-destructive">
                  {catalogError}
                </p>
              )}
              {!catalog && !catalogError && (
                <div className="flex items-center justify-center gap-2 py-16 text-sm text-foreground-muted">
                  <Loader2 className="size-4 animate-spin" aria-hidden /> Loading models…
                </div>
              )}

              {catalog && (
                <>
                  {/* Demo mode */}
                  {catalog.demo_available && (
                    <button
                      type="button"
                      onClick={() => setDraft(DEMO_CONFIG)}
                      aria-pressed={draft.mode === 'demo'}
                      className={`glass flex w-full cursor-pointer items-center justify-between rounded-2xl px-4 py-3 text-left transition-colors ${
                        draft.mode === 'demo' ? 'ring-2 ring-brand' : 'hover:border-brand/40'
                      }`}
                    >
                      <span>
                        <span className="flex items-center gap-2 text-sm font-bold">
                          <Sparkles className="size-4 text-brand" aria-hidden />
                          Demo mode — no key needed
                        </span>
                        <span className="mt-0.5 block text-xs text-foreground-muted">
                          Runs on free-tier open-source models (NVIDIA Nemotron via OpenRouter, Llama on
                          Groq) with a small daily quota — it can hit rate limits under load. Bring your
                          own key for reliable access and any model you like.
                        </span>
                      </span>
                      {draft.mode === 'demo' && <Check className="size-5 shrink-0 text-brand" aria-hidden />}
                    </button>
                  )}

                  {/* Provider cards */}
                  <div>
                    <p className="mb-2 text-xs font-bold uppercase tracking-wide text-foreground-muted">
                      Or connect a provider
                    </p>
                    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
                      {catalog.providers.map((p) => {
                        const look = PROVIDER_LOOK[p.id] ?? PROVIDER_LOOK.openrouter
                        const Icon = look.icon
                        const active = draft.mode === 'byok' && draft.provider === p.id
                        return (
                          <motion.button
                            key={p.id}
                            type="button"
                            onClick={() => pickProvider(p)}
                            whileHover={reduce ? undefined : { y: -3 }}
                            whileTap={reduce ? undefined : { scale: 0.97 }}
                            aria-pressed={active}
                            className={`glass relative flex cursor-pointer flex-col items-center gap-1.5 rounded-2xl px-2 py-3.5 transition-colors ${
                              active ? 'ring-2 ring-brand' : 'hover:border-brand/40'
                            }`}
                          >
                            {active && (
                              <motion.span
                                layoutId="provider-check"
                                className="absolute right-2 top-2 flex size-4 items-center justify-center rounded-full bg-brand text-white"
                              >
                                <Check className="size-3" aria-hidden />
                              </motion.span>
                            )}
                            <span
                              className={`flex size-9 items-center justify-center rounded-xl bg-gradient-to-br ${look.gradient} text-white`}
                            >
                              <Icon className="size-5" aria-hidden />
                            </span>
                            <span className="text-xs font-bold">{p.name}</span>
                            <span
                              className={`rounded-full px-1.5 py-0.5 text-[9px] font-extrabold tracking-wide ${KIND_BADGE[p.kind].cls}`}
                            >
                              {KIND_BADGE[p.kind].label}
                            </span>
                          </motion.button>
                        )
                      })}
                    </div>
                  </div>

                  {/* Selected provider detail */}
                  <AnimatePresence mode="wait">
                    {provider && draft.mode === 'byok' && (
                      <motion.div
                        key={provider.id}
                        initial={reduce ? { opacity: 0 } : { opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.22, ease: 'easeOut' }}
                        className="space-y-4"
                      >
                        <p className="text-sm text-foreground-muted">{provider.tagline}</p>

                        <KeySteps provider={provider} />

                        {/* Key input + validation */}
                        <div>
                          <label htmlFor="byok-key" className="mb-1.5 block text-xs font-bold">
                            {provider.name} API key <span className="text-destructive">*</span>
                          </label>
                          <div className="flex flex-col gap-2 sm:flex-row">
                            <div className="relative flex-1">
                              <input
                                id="byok-key"
                                type={showKey ? 'text' : 'password'}
                                value={draft.apiKey}
                                onChange={(e) => {
                                  setDraft((d) => ({ ...d, apiKey: e.target.value.trim() }))
                                  setValidation({ status: 'idle' })
                                }}
                                placeholder={`Paste your ${provider.name} key`}
                                autoComplete="off"
                                spellCheck={false}
                                className="min-h-[44px] w-full rounded-xl border border-border bg-surface px-3.5 pr-11 text-sm focus-visible:outline-none"
                              />
                              <button
                                type="button"
                                onClick={() => setShowKey((v) => !v)}
                                aria-label={showKey ? 'Hide key' : 'Show key'}
                                className="absolute right-1 top-1/2 flex size-9 -translate-y-1/2 cursor-pointer items-center justify-center rounded-lg text-foreground-muted hover:text-foreground"
                              >
                                {showKey ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
                              </button>
                            </div>
                            <button
                              type="button"
                              onClick={validate}
                              disabled={!draft.apiKey || validation.status === 'checking'}
                              className="flex min-h-[44px] cursor-pointer items-center justify-center gap-2 rounded-xl border border-border px-4 text-sm font-semibold transition-colors hover:border-brand/50 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {validation.status === 'checking' ? (
                                <Loader2 className="size-4 animate-spin" aria-hidden />
                              ) : (
                                <ShieldCheck className="size-4" aria-hidden />
                              )}
                              Test key
                            </button>
                          </div>
                          <div aria-live="polite">
                            {validation.status === 'ok' && (
                              <motion.p
                                initial={reduce ? undefined : { opacity: 0, y: 4 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="mt-1.5 flex items-center gap-1.5 text-xs font-semibold text-success"
                              >
                                <CheckCircle2 className="size-4" aria-hidden /> Key works — {validation.detail}
                              </motion.p>
                            )}
                            {validation.status === 'error' && (
                              <p className="mt-1.5 flex items-start gap-1.5 text-xs font-semibold text-destructive">
                                <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden /> {validation.detail}
                              </p>
                            )}
                          </div>
                          <p className="mt-1.5 text-[11px] text-foreground-muted">
                            Stored only in this browser. Sent straight through to {provider.name} on each
                            request — never saved on our servers.
                          </p>
                        </div>

                        {/* Model grid */}
                        <div>
                          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-foreground-muted">
                            Choose a model
                          </p>
                          <div className="grid gap-2.5 sm:grid-cols-2">
                            {provider.models.map((m, i) => (
                              <motion.div
                                key={m.id}
                                initial={reduce ? undefined : { opacity: 0, y: 8 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: reduce ? 0 : i * 0.04, duration: 0.2, ease: 'easeOut' }}
                              >
                                <ModelCard
                                  model={m}
                                  selected={draft.model === m.id}
                                  onSelect={() => pickModel(m)}
                                />
                              </motion.div>
                            ))}
                          </div>
                          {provider.allows_custom_model && (
                            <div className="mt-2.5">
                              <label htmlFor="custom-model" className="mb-1 block text-[11px] font-semibold text-foreground-muted">
                                Or paste any {provider.name} model ID
                              </label>
                              <input
                                id="custom-model"
                                value={customModel}
                                onChange={(e) => applyCustomModel(e.target.value)}
                                placeholder="e.g. deepseek/deepseek-chat-v3.1"
                                spellCheck={false}
                                className="min-h-[44px] w-full rounded-xl border border-border bg-surface px-3.5 text-sm focus-visible:outline-none"
                              />
                            </div>
                          )}
                        </div>

                        {/* Embeddings */}
                        {provider.embedding_models.length > 0 && (
                          <div className="rounded-2xl border border-border p-3.5">
                            <label className="flex cursor-pointer items-center justify-between gap-3">
                              <span>
                                <span className="block text-sm font-bold">
                                  Use my key for embeddings too
                                </span>
                                <span className="mt-0.5 block text-xs text-foreground-muted">
                                  Off = documents are indexed with DocChat's default embedder.
                                </span>
                              </span>
                              <input
                                type="checkbox"
                                checked={draft.byokEmbeddings}
                                onChange={(e) =>
                                  setDraft((d) => ({ ...d, byokEmbeddings: e.target.checked }))
                                }
                                className="size-5 shrink-0 cursor-pointer accent-[rgb(var(--brand))]"
                              />
                            </label>
                            {draft.byokEmbeddings && (
                              <div className="mt-3 space-y-2">
                                {provider.embedding_models.map((m) => (
                                  <label
                                    key={m.id}
                                    className="flex min-h-[44px] cursor-pointer items-center gap-2.5 rounded-xl border border-border px-3 py-2 text-sm has-[:checked]:border-brand"
                                  >
                                    <input
                                      type="radio"
                                      name="embed-model"
                                      checked={draft.embedModel === m.id}
                                      onChange={() => setDraft((d) => ({ ...d, embedModel: m.id }))}
                                      className="cursor-pointer accent-[rgb(var(--brand))]"
                                    />
                                    <span className="font-semibold">{m.name}</span>
                                    <span className="text-xs text-foreground-muted">{m.cost}</span>
                                    {m.recommended && (
                                      <span className="rounded-full bg-brand-2/15 px-2 py-0.5 text-[10px] font-bold text-brand-2">
                                        PICK
                                      </span>
                                    )}
                                  </label>
                                ))}
                                {pinMismatch && (
                                  <p className="flex items-start gap-1.5 rounded-xl bg-brand-2/10 px-3 py-2 text-xs font-medium text-foreground">
                                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-brand-2" aria-hidden />
                                    Your existing documents are indexed with “{catalog.embedding_pin}”.
                                    Questions will keep using that space; delete all documents to re-index
                                    with the new embedder.
                                  </p>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between gap-3 border-t border-border px-5 py-3.5">
              <p className="hidden text-[11px] text-foreground-muted sm:block">
                Model choice applies to your next question — switch anytime.
              </p>
              <div className="flex w-full items-center justify-end gap-2 sm:w-auto">
                <button
                  type="button"
                  onClick={onClose}
                  className="min-h-[44px] cursor-pointer rounded-xl px-4 text-sm font-semibold text-foreground-muted transition-colors hover:text-foreground"
                >
                  Cancel
                </button>
                {draft.mode === 'demo' ? (
                  <button
                    type="button"
                    onClick={saveDemo}
                    className="min-h-[44px] cursor-pointer rounded-xl bg-brand-gradient px-5 text-sm font-bold text-white shadow-glow transition-all hover:brightness-110"
                  >
                    Use demo mode
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={saveByok}
                    disabled={!canSave}
                    className="min-h-[44px] cursor-pointer rounded-xl bg-brand-gradient px-5 text-sm font-bold text-white shadow-glow transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
                  >
                    Save &amp; use {draft.modelName || 'model'}
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
