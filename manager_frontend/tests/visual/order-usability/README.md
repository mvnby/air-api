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

Scenarios run at 973×684, 390×844, 320×684 and 1440×900. They check:

- usable content height, a single footer row, full tab labels and no horizontal overflow;
- visible 44 px edit, delete and add actions, with Apply and Cancel together;
- the complete shell and order identity headers collapsing on downward workspace
  scroll, leaving section tabs visible and returning on upward scroll;
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

The focused full-shell regression suite also covers short three-service orders,
where collapsing the headers can consume all scroll overflow. Run it with the
same runtime overrides:

```sh
node manager_frontend/tests/visual/order-usability/scroll-headers.cjs
```

It records initial/down/up screenshots and full-stack geometry for both documents
and proposals at all four sizes. It checks stable automatic scroll clamping,
upward wheel and quick reversal during resizing, Home from the section navigation,
Shift+Tab returning to order controls, title/menu/account focus locks, and no order
save requests. `KITLANE_VIEWPORT` and `KITLANE_SCENARIO` (`documents` or
`short-proposal`) select a focused repeat; its default fixture port is 5204.

Recorded content heights, before and after scrolling down (all footer heights
were 61 px):

| Viewport | Content at top | Content while scrolling |
| --- | ---: | ---: |
| 973×684 | 363 px | 560 px |
| 390×844 | 490 px | 720 px |
| 320×684 | 314 px | 560 px |
| 1440×900 | 579 px | 776 px |

The top of the scrolled content is 63 px at every size; only section navigation
remains above it. Upward scroll restores the original stack.

Full-shell scrolling evidence: [973 px documents after scrolling](screenshots/973-documents-scrolled.png)
and [390 px documents after scrolling](screenshots/390-documents-scrolled.png).

Selected synthetic evidence: [medium screen overview](screenshots/973-overview.png),
[mobile service suggestions](screenshots/390-service.png), and
[visible invalid field on a narrow screen](screenshots/320-invalid-field.png).
