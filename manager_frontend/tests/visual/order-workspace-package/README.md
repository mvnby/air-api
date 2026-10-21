# Order workspace production benchmark

`capture.cjs` serves a frozen production `dist` and a read-only synthetic API on
localhost. Usage telemetry is acknowledged in memory; business mutations are
rejected. It never accesses production or modifies a real order. Both ordinary
and repair fixtures use synthetic order ID 477 and one populated draft proposal.

Run from the repository root with these environment variables:

```sh
KITLANE_PLAYWRIGHT_MODULE=/absolute/path/to/playwright \
KITLANE_BENCH_DIST=/absolute/path/to/frozen/dist \
KITLANE_BENCH_LABEL=before \
KITLANE_BENCH_PAIRS=5 \
KITLANE_BENCH_ICON_FONT=/absolute/path/to/material-icons.woff2 \
KITLANE_SCREENSHOTS=/absolute/path/to/results \
node manager_frontend/tests/visual/order-workspace-package/capture.cjs
```

Use the identical fixture, font file, browser version and settings for `after`.
The optional font file is a frozen copy of the application's Material Icons Round
font. The fixture server substitutes its external stylesheet URL with a local
stylesheet and serves the same font for both builds. This makes screenshots
reproducible without contacting external font services. All other served
application assets come from the supplied production build.

The fixed profile is Chromium at 384 × 850, mobile/touch enabled, CPU slowdown
4×, network latency 80 ms, download 200,000 bytes/s and upload 93,750 bytes/s.
Screenshots additionally show a 1440 × 850 viewport. Each pair creates a fresh
browser context for the cold run and reuses it with a new page for the warm run.
The cold run visits Documents and Work before warming the next page. Five pairs
provide five cold and five warm runs for each workflow. HTTP cache stays enabled;
the harness uses no browser request interception. Versioned assets are served
with immutable caching. API responses use `no-store`.

Readiness requires the fixture service text to be visible and the proposal's
`+ Услуга` action to pass a Playwright trial click. Startup requests include all
requests before the initial network-idle boundary, after readiness. Documents
readiness requires the provider toggle and loaded empty document list. Work
readiness requires the enabled worker selector and loaded worker-pay empty state.
Each section is opened, left for Proposal, and opened again. The fixed sequence
is Documents first/repeat, then Work first/repeat. Work's first visit can reuse
shared chunks already loaded by Documents; this does not measure an isolated
Work-first navigation path. Times include the observable UI click and response,
with the same selectors in both builds.

JSON artifacts retain every run, the actually requested startup JavaScript
filenames, API paths/methods, cache flags and CDP encoded transfer sizes. The
reported JavaScript gzip size sums gzip level 9 sizes of unique JavaScript files
actually requested by Chromium before the initial idle boundary. It is distinct
from CDP transferred bytes, which also include response headers and become zero
for genuinely cached responses. Every response is checked for HTTP errors and
each page for uncaught JavaScript errors. Medians are reported separately for
each cache and workflow combination.

These are controlled browser comparisons with small synthetic API responses,
not measurements of production backend latency, real customer data or production
server compression/cache policy. The fixture's populated line intentionally
avoids optional product lookup and installation recommendation requests. Other
regression harnesses own editing, save errors and navigation acceptance.

For deterministic behavioral screenshots, the sibling
`tests/visual/order-navigation/capture.cjs` accepts `KITLANE_ICON_FONT` pointing
to the same frozen Material Icons Round WOFF2 file. It substitutes only the
external font stylesheet/font responses; application assets and synthetic API
flows are unchanged. This avoids screenshot timeouts waiting for Google Fonts.
