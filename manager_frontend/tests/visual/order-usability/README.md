# Order workspace usability acceptance

The suite opens the real production Manager build with synthetic localhost order
and tariff data. It reuses the request/file fixture and records geometry, browser
errors, ordinary user actions, screenshots and `results.json`. Production order
and customer data are never read or changed.

Build once with `cd manager_frontend && npm run build`, then run from the repository
root with the installed Playwright runtime:

```sh
KITLANE_PLAYWRIGHT_MODULE=/path/to/node_modules/playwright \
KITLANE_CHROMIUM_PATH=/path/to/chromium \
KITLANE_SCREENSHOTS=/tmp/order-usability-acceptance \
node manager_frontend/tests/visual/order-usability/capture.cjs
```

The module/executable overrides are optional when Playwright and its browser are
already available. `KITLANE_FIXTURE_PORT` overrides the default local port 5203.

The nine scenarios run at 973×684, 390×844, 320×684 and 1440×900. They check:

- usable content height, a single footer row, full tab labels and no horizontal overflow;
- visible 44 px edit, delete and add actions, with Apply and Cancel together;
- one order header containing identity, direct autosave, stable save status/actions
  and the existing global profile/theme/brand controls;
- the combined header collapsing on downward workspace scroll, leaving section
  tabs visible and returning on upward scroll;
- full-width request context on constrained screens;
- document and payment content remaining open despite old collapsed preferences;
- full-width service suggestions populated from synthetic quick-add tariffs;
- draft confirmation on tab changes, continued editing after cancellation,
  validation focus and saving applied product/service rows before opening documents;
- correcting an invalid quantity under long product/service titles at 320×684,
  through both direct Apply and the navigation confirmation, with the field
  visible above the sticky action row.

Screenshots remain local review evidence. This fixture does not establish actual
production deployment or replace post-deployment smoke checks.

For a focused repeat after an error-handling change, set
`KITLANE_CASE=invalid-fields`. Other case names are `layout` and `drafts`.

The eight-case full-shell regression suite also covers short orders, where
collapsing the header can consume all scroll overflow. Run it with the
same runtime overrides:

```sh
node manager_frontend/tests/visual/order-usability/scroll-headers.cjs
```

It records initial/down/up screenshots and full-stack geometry for both documents
and proposals at all four sizes. It checks stable automatic scroll clamping,
upward wheel and quick reversal during resizing, Home from the section navigation,
Shift+Tab returning to order controls, title/menu/account focus locks, and no order
save requests. It also proves that an already fitting three-service order at
1440 px stays expanded, then uses four services to exercise actual scrolling;
two services at 390 px exercise overflow consumed by header collapse.
`KITLANE_VIEWPORT` and `KITLANE_SCENARIO` (`documents` or
`short-proposal`) select a focused repeat; its default fixture port is 5204.

The four state scenarios use the real header and synthetic API saves to cover
manual mode, dirty changes, a held in-flight save, failure/retry, saved and pending
line states. They check that toggle/status/action positions remain stable,
including a fast Home immediately after typing a new service at 320 px. Long
customer names use at most two mobile lines; the existing context panel exposes
the complete name. The 1440 px scenario checks a visible two-file count and
permanent context chevrons.

```sh
node manager_frontend/tests/visual/order-usability/header-states.cjs
```

This uses the same runtime overrides, optional `KITLANE_VIEWPORT`, default port
5206 and output directory `/tmp/order-unified-header-states`. Its PATCH requests
are deliberately limited to the local synthetic fixture.

The ordinary desktop header is 89 px. Expanded content starts at 152 px at
1440 px width (previously 260 px), and 200 px at 973 px width (previously 260 px).
The tablet keeps a separate context row; the wide screen shares that row with
section navigation. Normal mobile content starts at 274 px at both widths
(previously 293 px at 390 and 309 px at 320). Long names may use another line.

Recorded content heights, before and after scrolling down (all footer heights
were 61 px):

| Viewport | Content at top | Content while scrolling |
| --- | ---: | ---: |
| 973×684 | 423 px | 560 px |
| 390×844 | 509 px | 720 px |
| 320×684 | 349 px | 560 px |
| 1440×900 | 687 px | 776 px |

The top of the scrolled content is 63 px at every size; only section navigation
remains above it. Upward scroll restores the original stack.

Full-shell scrolling evidence: [973 px documents after scrolling](screenshots/973-documents-scrolled.png)
and [390 px documents after scrolling](screenshots/390-documents-scrolled.png).

Selected synthetic evidence: [medium screen overview](screenshots/973-overview.png),
[mobile service suggestions](screenshots/390-service.png), and
[visible invalid field on a narrow screen](screenshots/320-invalid-field.png).

Unified-header evidence: matching 973 px proposal [before](screenshots/unified-before-973.png)
and [after](screenshots/unified-after-973.png), expanded proposals at
[1440 px](screenshots/unified-after-1440.png) and
[390 px](screenshots/unified-after-390.png), a
[two-line mobile customer](screenshots/unified-long-customer-390.png), and
[save failure with direct retry at 320 px](screenshots/unified-save-error-320.png).

The six keyboard scenarios keep the layout viewport fixed at 390×844 or 320×684
while modelling only `visualViewport.height` (500/360 px) and `offsetTop` (0/80 px).
They use actual Chromium touch events and hit tests with synthetic catalog and
service suggestions. Run with the same Playwright/browser overrides:

```sh
node manager_frontend/tests/visual/order-usability/keyboard.cjs
```

The default fixture port is 5207; screenshots and `results.json` go to
`/tmp/order-keyboard-acceptance`. `KITLANE_CASE` selects a case name printed by the
suite. Coverage is bounded to four new-line Add/Cancel outcomes and two existing
row Cancel/revert outcomes. It checks long titles, price/quantity/upward scroll,
real suggestion selection, invalid Apply, first-touch command delivery and totals,
action geometry through focusout up to click, and release after viewport restore.
Manual mode must produce no order PATCH requests. No second tap is used.
Automatic focus, input, resize and validation must reveal the active field above
the actions. Intentional manual scrolling remains free to move that field out of
view; it must preserve compact chrome and usable Add/Cancel. A genuine focus
transition back to the quantity then verifies automatic reveal again.

Before the fix, all four original new-line touch checks left the editor open:
focusout moved the action row before click. At 320/360, returning headers also
reduced useful editing space to zero. Independent acceptance after the fix
confirmed 8/8 quantity/title first-touch outcomes and useful space of 224 px at
320/360/offset0, 287 px at offset80, and 364 px at 390/500. The ordinary nine-case
suite, including its unchanged 100 ms validation visibility checks, also passed.

This models viewport geometry and touch delivery; it does not emulate a native
IME or establish Android/iOS Safari behavior on a physical device.

Unedited evidence: the same 320/360 view [before](screenshots/keyboard-before-320.png)
and [after](screenshots/keyboard-after-320.png),
[catalog suggestions with accessible actions](screenshots/keyboard-catalog-320.png),
and [a service applied after its first touch](screenshots/keyboard-first-add-390.png).
