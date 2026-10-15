# Product reader browser acceptance

All captures use synthetic account, contact, price, stock and specification
fixtures. Real model names identify the scenario only; these fixture values
are not product claims or production API evidence.

- [Desktop reader](reader-desktop.png)
- [Mobile reader](reader-mobile.png)
- [Compact mobile filters](compact-mobile.png)

Start the local Manager Vite server, then run from the repository root:

```sh
KITLANE_PLAYWRIGHT_MODULE=/path/to/existing/playwright node manager_frontend/tests/visual/catalog-reader/capture.cjs
```

The browser blocks every origin except the local preview and intercepts all
API/login requests. Override `KITLANE_PREVIEW_URL` for another local port and
`KITLANE_SCREENSHOTS` for the output directory. Playwright belongs to the
verification runtime and is not a Manager application dependency.

Acceptance covers partner and owner readers, grouped specifications, safe
manual links, gallery enlargement and Escape, adding directly to the existing
24-hour basket, restoring that selection in the workspace, owner editing,
keyboard opening from the table, light/dark and 1440/1280/768/390/320 CSS px.
The document must have no horizontal overflow and no JavaScript errors.

The fixture's first model starts at 657 CSS px on a 390 px viewport after
compaction; the earlier full filter layout started at 1329 px in the audit.
This is a fixture comparison, not a production timing or usability study.

See the [reader contract](../../../../docs/adr/catalog-decision-workspace.md#shared-product-reader).
