# Proposal → document → one mail editor acceptance

Only localhost synthetic data is used. The real Manager production build runs in
Chromium; the fixture models API responses, document issue and mail transport.
It never calls production, modifies existing business documents or sends mail.
Backend service tests separately verify composition, signature and immutable files
with PostgreSQL and a substituted download/SMTP transport.

Build from `manager_frontend/` with `npm run build`. From the repository root:

```sh
KITLANE_PLAYWRIGHT_MODULE=/Users/Vadim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright \
KITLANE_CHROMIUM_PATH='/Users/Vadim/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing' \
KITLANE_SCREENSHOTS=/tmp/proposal-mail-acceptance \
node manager_frontend/tests/visual/proposal-mail/capture.cjs
```

The installed Playwright location and Chromium executable may be overridden for
another environment. Screenshots and `results.json` are saved in the output
folder. The capture checks 1440, 390 and 320 CSS pixels, document overflow and
browser page errors. It covers:

- A viewed draft alternative beside a selected sent proposal, saving the pending
  order edit before opening the offer workflow and creating the correct draft.
- Existing documents remain present; preparing an offer does not change proposal
  status or send a letter. Document issue is the existing explicit action.
- Installation-only order 590 shape, goods only, goods plus delivery, diagnostics
  plus repair, and maintenance; human signature, To/Cc/Bcc and actual saved files.
- One final send action, final manual edits saved before preview/approval/send,
  conflict, order-save error, definitive failure and unknown/lost send result.
- A lost create response keeps selection fixed and reuses its idempotency key;
  unavailable AI leaves an editable, sendable fallback and retains manual text.

For interactive independent acceptance, run:

```sh
node manager_frontend/tests/visual/proposal-mail/server.cjs
```

Open [the local order fixture](http://127.0.0.1:5198/manager/orders/590?company=999&site=minsk&proposalId=586&section=documents).
The local fixture control URLs are:

- `/__fixture/reset?kind=service`: order 590 shape with an issued offer.
- `/__fixture/reset?kind=mixed`: goods and delivery, without installation.
- `/__fixture/reset?kind=goods`: goods only.
- `/__fixture/reset?kind=repair`: diagnostics and repair.
- `/__fixture/reset?kind=maintenance`: maintenance.
- `/__fixture/reset?kind=service&alternative=true`: selected proposal 586 is sent;
  open the order with `proposalId=587` to prepare the viewed draft alternative.
- `/__fixture/reset?kind=service&failSave=true&alternative=true`: failed save.
- `/__fixture/state`: inspect captured draft, requests, approvals and send count.

Flags can also be changed by posting JSON to `/__fixture/flags`: `conflict`,
`unknown`, `failed`, `lostResponse`, `failAI`, `lostCreate`, `failCreate` and
`failSave`. The fixture server binds only `127.0.0.1`; its default port is 5198,
configurable with `KITLANE_FIXTURE_PORT`. Synthetic identities use `.test` email
addresses. This is browser evidence, not a physical mobile-device test or a real
provider-delivery test.
