/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                // Primary Kerala Palette - Dark Theme
                kerala: {
                    950: '#041c14', // Deepest jungle
                    900: '#062b1f', // Dark forest
                    800: '#0a3d2c', // Forest floor
                    700: '#0f5139', // Deep jungle
                    600: '#147347', // Monsoon green
                    500: '#1a9555', // Emerald
                    400: '#2eb860', // Fresh palm
                    300: '#5dd488', // Light green
                    200: '#98e5b3', // Mint
                    100: '#d4f4e0', // Pale mint
                    50: '#f0fdf5',  // Ghost white
                },

                // Accent Gold (Temple/Kasavu)
                gold: {
                    900: '#7a5800',
                    800: '#a07200',
                    700: '#c28f00',
                    600: '#d4a017',
                    DEFAULT: '#e5b72a',
                    400: '#f0c94d',
                    300: '#f7da7a',
                    200: '#fbe9a7',
                    100: '#fef5d4',
                    50: '#fffbeb',
                },

                // Accent Cyan (Backwaters)
                water: {
                    DEFAULT: '#0ea5e9',
                    dark: '#0284c7',
                    light: '#38bdf8',
                    glow: 'rgba(14, 165, 233, 0.4)',
                },

                // Card/Surface colors for dark theme
                surface: {
                    900: 'rgba(4, 28, 20, 0.95)',
                    800: 'rgba(6, 43, 31, 0.9)',
                    700: 'rgba(10, 61, 44, 0.85)',
                    glass: 'rgba(6, 43, 31, 0.75)',
                    card: 'rgba(10, 61, 44, 0.6)',
                },

                // Status
                status: {
                    safe: '#22c55e',
                    watch: '#f59e0b',
                    alert: '#ef4444',
                    critical: '#dc2626',
                }
            },

            fontFamily: {
                sans: ['Inter', 'system-ui', 'sans-serif'],
            },

            boxShadow: {
                'glow-green': '0 0 40px rgba(20, 115, 71, 0.4)',
                'glow-gold': '0 0 30px rgba(212, 160, 23, 0.35)',
                'glow-cyan': '0 0 30px rgba(14, 165, 233, 0.35)',
                'inner-glow': 'inset 0 0 60px rgba(20, 115, 71, 0.15)',
                'card': '0 4px 30px rgba(0, 0, 0, 0.4)',
                'card-hover': '0 8px 50px rgba(0, 0, 0, 0.5)',
            },

            backgroundImage: {
                'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
                'gradient-conic': 'conic-gradient(var(--tw-gradient-stops))',
                'hero-pattern': `
                    radial-gradient(ellipse 80% 50% at 50% -20%, rgba(20, 115, 71, 0.3), transparent),
                    radial-gradient(ellipse 60% 40% at 100% 0%, rgba(212, 160, 23, 0.15), transparent),
                    radial-gradient(ellipse 50% 30% at 0% 100%, rgba(14, 165, 233, 0.15), transparent)
                `,
            },

            animation: {
                'fade-in': 'fadeIn 0.6s ease-out',
                'slide-up': 'slideUp 0.5s ease-out',
                'pulse-glow': 'pulseGlow 3s ease-in-out infinite',
                'float': 'float 6s ease-in-out infinite',
                'shimmer': 'shimmer 2s infinite',
                'gradient-flow': 'gradientFlow 8s ease infinite',
            },

            keyframes: {
                fadeIn: {
                    '0%': { opacity: '0', transform: 'translateY(10px)' },
                    '100%': { opacity: '1', transform: 'translateY(0)' },
                },
                slideUp: {
                    '0%': { opacity: '0', transform: 'translateY(30px)' },
                    '100%': { opacity: '1', transform: 'translateY(0)' },
                },
                pulseGlow: {
                    '0%, 100%': { opacity: '0.6' },
                    '50%': { opacity: '1' },
                },
                float: {
                    '0%, 100%': { transform: 'translateY(0)' },
                    '50%': { transform: 'translateY(-15px)' },
                },
                shimmer: {
                    '0%': { backgroundPosition: '-200% 0' },
                    '100%': { backgroundPosition: '200% 0' },
                },
                gradientFlow: {
                    '0%, 100%': { backgroundPosition: '0% 50%' },
                    '50%': { backgroundPosition: '100% 50%' },
                },
            },
        },
    },
    plugins: [],
}
