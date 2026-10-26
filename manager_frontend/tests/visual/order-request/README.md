# Order request and original files acceptance

All scenarios use synthetic localhost data and the real production Manager build.
No production requests, mail sends, data backfills or original-file copies occur.
Backend tests separately prove PostgreSQL scope, read-only projection and hash
deduplication across existing private/mail links.

Build with `cd manager_frontend && npm run build`. From the repository root:

```sh
KITLANE_PLAYWRIGHT_MODULE=/Users/Vadim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright \
KITLANE_CHROMIUM_PATH='/Users/Vadim/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing' \
KITLANE_SCREENSHOTS=/tmp/order-request-acceptance \
node manager_frontend/tests/visual/order-request/capture.cjs
```

Override the module and executable for the installed Playwright/Chromium runtime.
The capture uses port 5200 by default (`KITLANE_FIXTURE_PORT` can override it),
checks actual 1440/390/320 px geometry and ordinary clicks, saves PNG evidence,
downloaded synthetic PDFs and `results.json`. It covers email with two original
PDFs and long text/names, tender, manual and empty orders, unavailable legacy
files, metadata/access errors and retry, loading, order-navigation races,
Escape/focus restoration, unfinished proposal edits and tab changes. The
component suite additionally checks an unfinished object comment.

For independent interactive acceptance:

```sh
node manager_frontend/tests/visual/order-request/server.cjs
```

Open [the synthetic order](http://127.0.0.1:5199/manager/orders/590?company=999&site=minsk&proposalId=586).
Use `/__request/reset?scenario=email`, `tender`, `manual`, `empty`, `unavailable`
or `error` to reset scenarios, then reload the order page. `/__request/state`
shows metadata reads, original accesses and attempted business mutations.
`POST /__fixture/flags` accepts `contextDelay` (milliseconds), `contextError`
and `accessError`. The shared fixture's order PATCH records explicit edits.
Order 591 is a second synthetic order; open it without `proposalId` to test
navigation. The fixture cannot prove actual production file availability or
production layout until the accepted build is deployed and smoke-checked.
