# Vue 3 + TypeScript + Vite

This template should help get you started developing with Vue 3 and TypeScript in Vite. The template uses Vue 3 `<script setup>` SFCs, check out the [script setup docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup) to learn more.

Learn more about the recommended Project Setup and IDE Support in the [Vue Docs TypeScript Guide](https://vuejs.org/guide/typescript/overview.html#project-setup).

## KitLane presentation tokens

`src/styles/kitlane-tokens.css` is the shared source for brand shades, semantic
surface/text colors and the font stack. Use `brand-*` utilities for primary
buttons, selected tabs, focus, links and decorative accents; Tailwind maps them
to these tokens, including opacity modifiers and dark variants. Do not introduce
new hard-coded teal accents or redefine the Tailwind `teal` color globally.

Keep success, payment, warning and workflow status colors semantic. Existing
workflow stages may intentionally retain teal. For handwritten CSS, prefer
`--kitlane-accent-text` for foregrounds and `--kitlane-accent` for filled actions;
text colors must remain readable in both themes. The customer view's scoped
presentation rules live in `src/styles/customers.css`.
