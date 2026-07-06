import typography from '@tailwindcss/typography'

/** Semantic tokens resolve to CSS variables (see index.css) so a single
 *  `.dark` class flips the whole palette. `<alpha-value>` keeps Tailwind's
 *  opacity modifiers (bg-brand/10, text-foreground-muted/60) working. */
const withAlpha = (v) => `rgb(var(${v}) / <alpha-value>)`

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        background: withAlpha('--bg'),
        surface: withAlpha('--surface'),
        'surface-muted': withAlpha('--surface-muted'),
        border: withAlpha('--border'),
        foreground: withAlpha('--foreground'),
        'foreground-muted': withAlpha('--foreground-muted'),
        brand: withAlpha('--brand'),
        'brand-2': withAlpha('--brand-2'),
        accent: withAlpha('--accent'),
        success: withAlpha('--success'),
        destructive: withAlpha('--destructive'),
        ring: withAlpha('--ring'),
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.125rem',
        '3xl': '1.75rem',
      },
      boxShadow: {
        glow: '0 0 0 1px rgb(var(--brand) / 0.15), 0 12px 40px -12px rgb(var(--brand) / 0.45)',
        'glow-accent': '0 12px 40px -12px rgb(var(--accent) / 0.55)',
        soft: '0 4px 24px -8px rgb(2 6 23 / 0.12)',
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--brand-2)))',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translate3d(0,0,0) scale(1)' },
          '33%': { transform: 'translate3d(3%, -4%, 0) scale(1.08)' },
          '66%': { transform: 'translate3d(-3%, 3%, 0) scale(0.96)' },
        },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
      },
      animation: {
        float: 'float 18s ease-in-out infinite',
        'float-slow': 'float 26s ease-in-out infinite',
        'fade-up': 'fade-up 0.5s cubic-bezier(0.16,1,0.3,1) both',
        'fade-in': 'fade-in 0.4s ease-out both',
        blink: 'blink 1s step-end infinite',
      },
    },
  },
  plugins: [typography],
}
