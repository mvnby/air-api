/** @type {import('tailwindcss').Config} */
export default {
    darkMode: 'class',
    content: [
        "./index.html",
        "./src/**/*.{vue,js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                brand: Object.fromEntries(
                    [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map(
                        shade => [shade, `rgb(var(--kitlane-brand-${shade}) / <alpha-value>)`],
                    ),
                ),
            },
            fontFamily: { sans: ['var(--kitlane-font-sans)'] },
        },
    },
    plugins: [],
}
