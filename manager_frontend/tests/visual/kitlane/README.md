# KitLane visual review — issue #993

This directory contains only synthetic company/account/financial fixtures. The
owner's private source screenshot and brief are not included. `brands.html` is a
local Vite test entry, not an application route or part of the production build.

## Review images

| State | Image |
| --- | --- |
| Before, synthetic dashboard | [Before](screenshots/before-desktop-light.png) |
| Desktop light; no company logo | [Light](screenshots/after-desktop-light.png) |
| Desktop dark | [Dark](screenshots/after-desktop-dark.png) |
| Mobile, 390 CSS px | [Mobile](screenshots/after-390.png) |
| Collapsed sidebar | [Collapsed](screenshots/after-collapsed.png) |
| Logo fallback and shape fixtures | [Brands](screenshots/after-logo-fixtures.png) |

No screenshots claim live API integration for company logos. All dashboard API
calls, formatting, comparison periods and calculations are unchanged. The
existing dashboard formats monetary values as BYN; this PR does not change that
existing behavior or copy currencies from the concept.

## Brand source and boundary

`useKitlaneIdentity` reads the existing `managerStorefrontSelection` list loaded
by the authenticated session bootstrap from `GET /api/manager/storefronts`.
It uses the selected allowed storefront's `display_name`; employee
`auth.display_name` stays exclusively in the account menu. Unknown/loading,
switching, logout and session recovery reset the company title to `KitLane`.
The new identity component has optional full/compact image props and image error
fallbacks. Production currently passes neither image prop.

Checked `ManagerAuthStatusResponse`, `ManagerStorefrontResponse`, Tenant/Storefront
models, Manager settings and the public content serializer. There is no exposed
company-logo field in these contracts. Manufacturer `Brand.logo_url` and document
company requisites are not suitable substitutes. The shared authorized logo
contract is tracked separately in [#994](https://github.com/mvnby/air-api/issues/994).

## Changes

- `App.vue`: connects extracted shell/navigation and authorized partner identity;
  existing route/capability/session/rebuild logic remains here (564 lines).
- `components/kitlane/`: shell, sidebar navigation, partner identity and platform
  mark/wordmark. Mobile drawer has Escape, focus containment and focus return.
- `styles/kitlane-tokens.css`, `style.css`: light/dark semantic tokens, compatible
  `--mv-*` aliases, common controls/focus; no additional global `!important` layer.
- `ManagerAccountMenu`, login and storefront presentation: compact account and
  theme layout, accessible menu keys, safe login branding. Storefront event binding
  now retains its selection-service receiver; a real browser click previously
  failed to switch. The service itself and its authorization contract are unchanged.
- `ManagerHome`, `components/dashboard`: tabs, cards, chart/action accents, responsive
  attention grid and KPI typography; semantic success/error/warning colors remain.
- `index.html`, `public/kitlane-mark*.svg`: favicon and working vector assets v1.
- Component and browser verification fixtures in `tests/`.

## Validation

Run application checks from `manager_frontend/`:

```sh
npm run build
npm run test:ui-logic
npm run test:components
```

Recorded: production build passed; UI logic/native-dialog audit passed; full
component suite passed 66 files / 301 tests. The brand suite is explicitly in
`test:components`, including failed images, unknown context, long name, independent
compact mark fallback, title reset, and storefront event dispatch. Existing session
boundary/recovery, capabilities, account, storefront, home and dashboard suites pass.

For browser capture, first run the local Vite dev server, then from repository root:

```sh
KITLANE_PLAYWRIGHT_MODULE=/path/to/existing/playwright node manager_frontend/tests/visual/kitlane/capture.cjs
```

Playwright is supplied by the verification environment, not added to Manager's
package dependencies. The capture process permits only a local preview origin,
intercepts all API/login requests, and blocks other origins. Output defaults to
`.codex-tmp/kitlane`; it is not automatically committed. Optional overrides:
`KITLANE_PREVIEW_URL` and `KITLANE_SCREENSHOTS`.

Browser checks: light/dark and persistence across reload, 1440/1280/768/390/320 CSS
px, collapsed sidebar, mobile drawer and account popover, storefront reload and
name change, long title, logout/title reset, login light/dark, SEO/advertising tabs,
and full/compact wide/square/transparent/broken logo fixtures. No JavaScript errors
or document-level horizontal overflow. Also checked 640 CSS px (1280 px window at
200% zoom equivalent) with root text enlarged to 20 px; this does not claim a
physical browser zoom-control test or screen-reader certification.

Contrast checks for the new palette: white on primary blue 5.27:1; sidebar muted
text on hover surface 6.59:1; dark muted text on cards 7.32:1; control borders on
light/dark input backgrounds 3.25:1 and 4.50:1. Light muted text was darkened from
the starting palette to meet 4.5:1 on the page background. Card separators are
structural decoration rather than the only way to identify controls.

Merge and deployment require the owner's visual acceptance under #993. No merge,
production deployment, production API/data operations or public-storefront changes
are part of this review.
