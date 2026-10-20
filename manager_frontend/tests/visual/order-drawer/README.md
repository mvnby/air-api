# Order page navigation and mobile regression

Run the Manager dev or preview server, then from the repository root:

```sh
KITLANE_PLAYWRIGHT_MODULE=/path/to/existing/playwright node manager_frontend/tests/visual/order-drawer/capture.cjs
```

Playwright comes from the verification environment, not Manager dependencies.
Only a localhost server is allowed; API responses are synthetic. External
requests are blocked except the existing Google Fonts icon stylesheet/font. `KITLANE_PREVIEW_URL` selects the server (default
`http://127.0.0.1:5184`); `KITLANE_SCREENSHOTS` selects the output folder
(default `.codex-tmp/order-page`).

The full app is checked at 320, 360, 384, 412, 768 and 1440 CSS pixels:

- Every old order URL opens a standalone page without fetching the orders list.
- Canonical URLs survive reload, preserving proposal and return context.
- Horizontal touch gestures, zooming in and out, and a shorter viewport keep
  the page, scrolling content and proposal footer inside the visible screen.
- Mobile and desktop board navigation restores toolbar and column filters,
  expanded orders, vertical scroll and horizontal board position.
- Pending edits save before returning. A failed save blocks browser Back and
  retains the draft; navigation works again after recovery.

Screenshots and measurements are saved locally. This does not claim testing on
physical Android hardware or simulating the native software keyboard itself.
