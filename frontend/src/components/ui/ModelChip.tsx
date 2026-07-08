import { useEffect, useState } from 'react'
import { Brain, ChevronDown, Gem, Route, Sparkles, Zap } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { loadLLMConfig, onLLMConfigChange } from '../../lib/llmConfig'

const PROVIDER_ICON: Record<string, typeof Zap> = {
  groq: Zap,
  openrouter: Route,
  openai: Sparkles,
  anthropic: Brain,
  gemini: Gem,
  demo: Sparkles,
}

/** The always-visible "which model am I on?" chip — opens the Model Studio. */
export function ModelChip({ onClick }: { onClick: () => void }) {
  const reduce = useReducedMotion()
  const [config, setConfig] = useState(loadLLMConfig)

  useEffect(() => onLLMConfigChange(() => setConfig(loadLLMConfig())), [])

  const Icon = PROVIDER_ICON[config.provider] ?? Sparkles
  const label =
    config.mode === 'demo'
      ? 'Demo · free tier'
      : `${config.modelName || config.model}`

  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileHover={reduce ? undefined : { y: -1 }}
      whileTap={reduce ? undefined : { scale: 0.97 }}
      title="Change AI model"
      className="flex min-h-[36px] max-w-[220px] cursor-pointer items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-foreground-muted transition-colors hover:border-brand/50 hover:text-foreground"
    >
      <span className="flex size-4 items-center justify-center text-brand">
        <Icon className="size-3.5" aria-hidden />
      </span>
      <span className="truncate">{label}</span>
      {config.mode === 'byok' && (
        <span className="rounded-full bg-brand/10 px-1.5 py-0.5 text-[9px] font-extrabold text-brand">
          YOUR KEY
        </span>
      )}
      <ChevronDown className="size-3 shrink-0" aria-hidden />
    </motion.button>
  )
}
