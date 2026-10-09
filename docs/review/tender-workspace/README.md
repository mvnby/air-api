# Procurement workspace browser acceptance

These captures use the actual Vue components in a local fixture with synthetic
data and mocked API responses. Desktop width is 1440px; mobile width is 390px.
Remote HTTP(S) requests were blocked, so icon-font placeholders appear as dots.
The fixture is not a production screenshot or evidence of a real email delivery.

| Flow | Desktop | Mobile |
| --- | --- | --- |
| Stage, deadline and archived price-enquiry association | [Capture](desktop-tender.png) | [Capture](mobile-tender.png) |
| Private certificate versions in issuer settings | [Capture](desktop-settings.png) | [Capture](mobile-settings.png) |
| Explicit certificate-only email with no order documents | [Capture](desktop-certificate-email.png) | [Capture](mobile-certificate-email.png) |
| First-use statement with no existing statement template | [Capture](desktop-participant-fields.png) | [Capture](mobile-participant-fields.png) |
| Factual confirmation before issuing the statement | [Capture](desktop-participant-confirmation.png) | [Capture](mobile-participant-confirmation.png) |

The browser exercised stage/deadline saving, selecting an archived earlier
enquiry, certificate version selection, desktop upload, and certificate-only
compose/send with an explicit issuer and empty document IDs. Statement creation
worked without a pre-existing template. Issue stayed disabled until the factual
confirmation was checked, and the mocked issue request carried that confirmation.
The declaration textarea displayed multiple lines. No horizontal page overflow
or browser page errors occurred. All delivery calls were mocked; no production
business records, certificates or emails were created.
