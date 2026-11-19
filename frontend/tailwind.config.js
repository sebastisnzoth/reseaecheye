/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      // Allow any /N opacity modifier used by the design system (e.g. /8, /12).
      opacity: Object.fromEntries(Array.from({ length: 101 }, (_, i) => [i, String(i / 100)])),
      colors: {
        ink: {
          950: '#050b13',
          900: '#08131f',
          850: '#0b1a28',
          800: '#0f2232',
          700: '#173448',
        },
        aqua: {
          300: '#6ee7de',
          400: '#34d6c8',
          500: '#12b8ac',
          600: '#0b8c88',
        },
        signal: {
          amber: '#f2b65a',
          rose: '#f2708a',
          violet: '#a996fa',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(52,214,200,0.12), 0 24px 70px -30px rgba(18,184,172,0.45)',
        card: '0 20px 60px -40px rgba(0,0,0,0.9)',
      },
      keyframes: {
        floaty: { '0%,100%': { transform: 'translateY(0px)' }, '50%': { transform: 'translateY(-8px)' } },
        pulseSoft: { '0%,100%': { opacity: '0.55' }, '50%': { opacity: '1' } },
      },
      animation: {
        floaty: 'floaty 8s ease-in-out infinite',
        pulseSoft: 'pulseSoft 2.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
