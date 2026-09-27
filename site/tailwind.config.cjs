const path = require('path')
const docs = path.join(__dirname, '..', 'docs')

/** Tailwind yapilandirmasi - docs/ altindaki tum sayfalar icin statik CSS uretir.
 *  Play CDN kaldirildi; uretilen dosya: docs/assets/site.css
 */
module.exports = {
  darkMode: 'class',
  content: [
    path.join(docs, '**/*.html'),
    path.join(docs, 'assets/consent.js'),
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        cookie: {
          50: '#fffbeb',
          100: '#fef3c7',
          200: '#fde68a',
          300: '#fcd34d',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
          800: '#92400e',
          900: '#78350f',
        },
        surface: {
          base: '#08090d',
          card: '#10121a',
          cardHover: '#161924',
          border: '#1e2333',
          borderLight: '#2c3349',
        },
      },
      animation: {
        glow: 'glow 5s ease-in-out infinite alternate',
      },
      keyframes: {
        glow: {
          '0%': { opacity: 0.35, transform: 'scale(0.98)' },
          '100%': { opacity: 0.65, transform: 'scale(1.02)' },
        },
      },
    },
  },
  plugins: [],
}
