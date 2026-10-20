# Order drawer viewport regression

Run the Manager dev or preview server, then from the repository root:

```sh
KITLANE_PLAYWRIGHT_MODULE=/path/to/existing/playwright node manager_frontend/tests/visual/order-drawer/capture.cjs
```

Playwright comes from the verification environment, not Manager dependencies.
Only a localhost server is allowed; API responses are synthetic and external
requests are blocked. `KITLANE_PREVIEW_URL` selects the server (default
`http://127.0.0.1:5184`); `KITLANE_SCREENSHOTS` selects the output folder
(default `.codex-tmp/order-drawer`).

The check opens an order through the full app at 320, 360, 384, 412, 768 and
1440 CSS pixels, then makes the background page 1800 pixels wide. The drawer,
scrolling content and footer must stay inside the viewport, including when the
background scroll lock is deliberately removed. A shorter mobile viewport and
closing the drawer are also checked. Screenshots and measurements are saved
locally; this does not claim testing on a physical Android device.
