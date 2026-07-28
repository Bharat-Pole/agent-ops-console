/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: 'var(--bg-canvas)',
        surface: 'var(--bg-surface)',
        raised: 'var(--bg-raised)',
        nav: 'var(--bg-nav)',
        border: 'var(--border)',
        'border-strong': 'var(--border-strong)',
        'text-hi': 'var(--text-hi)',
        'text-mid': 'var(--text-mid)',
        'text-low': 'var(--text-low)',
        accent: 'var(--accent)',
        'accent-new': 'var(--accent-new)',
        ok: 'var(--ok)',
        warn: 'var(--warn)',
        err: 'var(--err)',
        info: 'var(--info)',
        'tier-minimal': 'var(--tier-minimal)',
        'tier-standardized': 'var(--tier-standardized)',
        'tier-advanced': 'var(--tier-advanced)',
        'risk-low': 'var(--risk-low)',
        'risk-medium': 'var(--risk-medium)',
        'risk-high': 'var(--risk-high)',
        'risk-critical': 'var(--risk-critical)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        card: '8px',
        control: '6px',
      },
      fontSize: {
        base: ['14px', '20px'],
        title: ['20px', '28px'],
      },
    },
  },
  plugins: [],
};
