# DocChat — Design System

> ## v2 (current) — light-first, colorful, glassmorphism
> The v1 dark-only / green-accent / Inter system below is superseded. DocChat now ships a
> **light-first, colorful glassmorphism** UI with a **dark-mode toggle**. Tokens are CSS
> variables in `src/index.css` (light on `:root`, dark on `.dark`) and Tailwind maps them
> as `rgb(var(--x) / <alpha-value>)` so opacity modifiers keep working. Only use the
> semantic Tailwind names in components — never raw hex.

### Style
Light default, airy, with an **ambient gradient mesh** (three slowly-drifting blurred
color blobs behind everything, `components/ui/GradientMesh.tsx`) and **frosted-glass**
surfaces for every panel/card. Dark mode is a full sibling theme, not an afterthought —
both are defined together. Theme lives in `lib/theme.tsx` (persisted, honours OS dark pref
on first visit only), toggled via `components/ui/ThemeToggle.tsx`.

### Color tokens (semantic → CSS var)
| Token | Light | Dark | Use |
|---|---|---|---|
| `background` | near-white lavender | deep navy `#080B1A` | app shell (behind the mesh) |
| `surface` / `surface-muted` | white / `#F4F5FC` | `#11162B` / `#181E36` | opaque panels, doc cards |
| `border` | `#E2E4F0` | `#2A3252` | dividers, input/card borders |
| `foreground` / `foreground-muted` | slate-900 / slate-500 | slate-200 / slate-400 | text |
| `brand` / `brand-2` | indigo-500 / purple-500 | lightened for dark | gradient CTAs, links, citations, progress |
| `accent` | blue-600 | blue-400 | secondary highlight |
| `success` / `destructive` | emerald / rose | lightened | health dot / errors, delete |
| `ring` | indigo | indigo | keyboard focus |

**Glass surfaces** are not Tailwind colors — use the `.glass` / `.glass-strong` component
classes (defined in `index.css`): translucent bg + `backdrop-blur` + theme border + soft
shadow, so they carry per-theme translucency in one place. `bg-brand-gradient` +
`shadow-glow` is the signature primary-CTA look; `.text-gradient` for headline/wordmark.

**Focus:** a global `*:focus-visible` ring (double box-shadow, brand-tinted, works on both
themes) is defined in `index.css` — components no longer need per-element ring utilities.

### Typography
**Plus Jakarta Sans** (Google Fonts, `@import` in `index.css`) for both UI and body —
friendly, modern SaaS personality. Weights: 400 body, 500 labels, 600 headings, 700/800
display. Scale unchanged: `text-sm` metadata, `text-base` body/chat, `text-lg`→`text-6xl`
for headings/hero.

---

## v1 (superseded) — retained for provenance
The sections below describe the original dark-only demo UI. Structural component guidance
(hit areas, drawer behavior, reduced-motion, mobile bottom-sheet) still applies; the
dark-only palette, `#22C55E` accent, Inter font, and "24h auto-delete" copy do not.

### Style
**Dark Mode (OLED)** — dark-only, no light mode.

### Typography
**Inter** for both UI and body text.

## Component guidance

### Sidebar (`Sidebar.tsx`, `Dropzone.tsx`, `DocCard.tsx`, `IngestProgress.tsx`)
- Sidebar surface: `bg-surface border-r border-border`. Fixed width `w-80` on desktop
  (`lg:` breakpoint+), collapses to a bottom sheet below `lg` (see mobile section).
- Dropzone: dashed `border-2 border-dashed border-border rounded-lg`, `hover:border-accent`
  on drag-over, min touch-friendly padding (`p-8`) so the whole zone is a large tap target.
- DocCard: `bg-surface-muted rounded-lg p-3 gap-2`, filename truncates with ellipsis
  (`truncate`) not multi-line wrap — full name in `title` attr for hover/long-press.
  Delete icon button: `size-11` (44px) hit area even though the icon itself is `size-4`,
  per touch-target-size rule — use padding, not a bigger icon.
- IngestProgress: thin bar, `bg-border` track / `bg-accent` fill, animate width with
  `transition-[width] duration-300 ease-out`. Do not animate on every SSE tick if ticks
  arrive faster than ~16ms apart — throttle to avoid layout thrash.
- "Auto-delete after 24h" note: `text-sm text-foreground-muted`, pinned to sidebar bottom.

### Chat panel (`Chat.tsx`, `MessageList.tsx`, `Composer.tsx`)
- User messages: right-aligned bubble, `bg-accent/10 border border-accent/20 text-foreground
  rounded-2xl rounded-br-sm`. Assistant messages: left-aligned, no bubble — flush text on
  `bg-background` (chat-tool convention: only the human's turn gets a bubble, keeps the
  streamed answer feeling like a document, not a chat cliché).
- Composer: `bg-surface border-t border-border`, input `min-h-[44px]`, send button
  `bg-accent text-background` with disabled state `opacity-40 cursor-not-allowed` (per
  disabled-states rule: 0.38–0.5 opacity) plus a tooltip explaining "upload a document first."
- Starter questions (empty state): 3 pill buttons, `border border-border rounded-full
  px-4 py-2 hover:border-accent hover:bg-surface`, wrap on mobile (`flex-wrap`).
- Streaming cursor: a blinking `▍` or 2px accent bar at the end of in-flight text —
  motion must respect `prefers-reduced-motion` (swap to static, no blink).

### Citation chips (`CitationChip.tsx`)
- Inline `<button>` not `<span>` (must be keyboard/tab reachable, opens the drawer).
  `bg-accent/15 text-accent text-sm font-medium rounded px-1.5 leading-none align-super`,
  `hover:bg-accent/25`. Number only (`[1]`), no icon — keep inline text rhythm intact.
- Uncited sources in the drawer are dimmed (`opacity-50`) per spec — never conveyed by
  color alone, so also add a small "not cited" label, not just dimming (color-not-only rule).

### Sources drawer (`SourcesDrawer.tsx`)
- Desktop: right-side slide-in panel, `w-96 bg-surface-muted border-l border-border`,
  `transition-transform duration-300 ease-out` (translate-x, not width — animate transform
  only, never layout-affecting properties).
- Mobile: becomes a bottom sheet (`fixed inset-x-0 bottom-0 rounded-t-2xl`, max-height
  `80dvh` not `80vh`), dismiss via swipe-down or an explicit close button — never
  gesture-only (must have a visible close affordance per modal-escape rule).
- Scrim behind the drawer: `bg-black/50` minimum (40–60% black per scrim-legibility rule)
  so the chat behind doesn't compete visually.
- Opening a citation scrolls the drawer to the matching source and highlights it briefly
  (`bg-accent/10` flash, ~400ms fade) — gives the click a visible destination.

### Empty / error states (`EmptyState.tsx`, `ErrorBanner.tsx`)
- ErrorBanner (backend unreachable, 429, SSE failure): `bg-destructive/10 border
  border-destructive/30 text-foreground`, icon (Lucide `AlertTriangle`, not emoji) +
  message + action (retry button) — never a bare message with no recovery path.
- EmptyState (no docs yet): centered icon + one-line copy + the dropzone CTA is enough;
  don't duplicate the sidebar's dropzone as a second dropzone here.

## Mobile behavior (sidebar → bottom sheet)
Below `lg` (1024px): sidebar hides by default, a header bar shows a "Documents (n)" pill
that opens the same `Sidebar` content as a bottom sheet (`fixed inset-x-0 bottom-0
max-h-[85dvh] rounded-t-2xl`, scrim behind). Reuse one `Sidebar` component; only the
container (`aside` vs. sheet) changes by breakpoint — do not fork the component.
Use `min-h-dvh` for the app shell root, not `h-screen` (mobile browser chrome rule).

## Icons
Lucide React (`lucide-react`) throughout — `UploadCloud`, `FileText`, `Trash2`, `X`,
`AlertTriangle`, `Send`, `Loader2` (spin for progress). No emoji anywhere in the UI.
Stroke width consistent at `1.75` across all icons; size tokens `size-4` (inline/chip),
`size-5` (buttons), `size-6` (empty-state hero icon) — no arbitrary sizes.

## Pre-delivery checklist (carry into E5 acceptance criteria)
- [ ] All interactive elements ≥44×44px hit area (delete buttons, chips, close icons)
- [ ] Focus-visible ring on every button/input/chip, tab order matches visual order
- [ ] `prefers-reduced-motion` disables the streaming cursor blink and drawer slide (swap to fade or instant)
- [ ] Contrast: `foreground` on `background`/`surface` ≥4.5:1 (verified: #F8FAFC on #0F172A ≈ 17:1, passes AAA)
- [ ] No horizontal scroll at 375px; sources drawer bottom-sheet tested at 375px and landscape
- [ ] Citation chip and delete-doc icon both keyboard-operable (Enter/Space), not click-only
