import type { SourceItem } from '../api/types'

const CITATION_RE = /\[(\d+)\]/g

/** Turns final `[n]` markers into markdown links (`[n](citation:n)`) so
 * react-markdown's `a` renderer can swap them for a CitationChip. Numbers with
 * no matching source are stripped — the model cited something that doesn't
 * exist (ARCHITECTURE §5.4 safety net). During streaming, leave `[n]` as
 * plain text (spec: "during streaming plain [n] is fine"). */
export function annotateCitations(text: string, sources: SourceItem[]): string {
  const validNs = new Set(sources.map((s) => s.n))
  return text.replace(CITATION_RE, (_match, numStr) => {
    const n = Number(numStr)
    return validNs.has(n) ? `[${n}](citation:${n})` : ''
  })
}
