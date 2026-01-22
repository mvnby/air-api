# AI Agent Prompt: New Site Pages

**Context:**
We are building a site for "Master Air" (Air conditioning in Vitebsk). Stack: Astro + Vue.

**Goal:**
Implement the following pages with a premium, responsive design (TailwindCSS).

1.  **Contacts Page (`/contacts`)**:
    *   Component: `ContactForm.vue` (Name, Phone, Comment).
    *   Layout: Grid with Info on left, Form on right.

2.  **Services Pages (`/services/*`)**:
    *   Structure:
        *   `/services/installation` (Монтаж)
        *   `/services/maintenance` (Обслуживание)
        *   `/services/repair` (Ремонт)
    *   Content: Each page needs a specific Hero title, distinct benefits list, and a price block.

3.  **Calculator Page (`/selection`)**:
    *   Component: `PowerCalculator.vue`.
    *   Logic: Simple multiplier (Area * 1kW/10m2).
    *   UI: Interactive slider for area.

**Style Guide:**
*   Use `<Layout>` wrapper.
*   Primary Color: Teal (`#007f80`).
*   Glassmorphism effects for cards.
*   Micro-animations on buttons/inputs.
