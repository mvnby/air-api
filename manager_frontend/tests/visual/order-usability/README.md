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
- context controls collapsing on downward scroll and returning on upward scroll;
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

Recorded content heights, before and after scrolling down (all footer heights
were 61 px):

| Viewport | Content at top | Content while scrolling |
| --- | ---: | ---: |
| 973×684 | 363 px | 411 px |
| 390×844 | 490 px | 538 px |
| 320×684 | 314 px | 362 px |
| 1440×900 | 579 px | 627 px |

Selected synthetic evidence: [medium screen overview](screenshots/973-overview.png),
[mobile service suggestions](screenshots/390-service.png), and
[visible invalid field on a narrow screen](screenshots/320-invalid-field.png).
