# Trusted public storefront context

## Purpose

Public Lead and Order provenance must come from the storefront serving the
request, never from a browser-provided tenant or storefront ID. The canonical
MVN website keeps working without extra headers. A second storefront is enabled
only through a short-lived context signed by its trusted SSR or edge proxy.

## Request envelope

The trusted runtime sends all three headers:

- `X-MVN-Storefront-Host`: normalized public hostname, for example
  `orsha.mvn.by`;
- `X-MVN-Storefront-Timestamp`: Unix timestamp in seconds;
- `X-MVN-Storefront-Signature`: `v1=<lowercase sha256 hex>`.

The HMAC-SHA256 input is UTF-8 text with no trailing newline:

```text
v1
<timestamp>
<UPPERCASE HTTP method>
<request path beginning with />
<lowercase IDNA hostname without port or trailing dot>
```

The signing key is `STOREFRONT_CONTEXT_SIGNING_SECRET` and must contain at
least 32 bytes. The API accepts a timestamp no more than
`STOREFRONT_CONTEXT_MAX_AGE_SECONDS` in the past or future; the allowed range
for that setting is 30–900 seconds.

Signatures are bound to method, path and hostname. Query parameters and request
bodies are deliberately excluded: this envelope selects public provenance; it
does not replace endpoint validation, idempotency or authentication.

## Fail-closed behaviour

- no context headers: resolve canonical active `mvn/main` exactly as before;
- incomplete, malformed, expired or forged envelope: `401`;
- envelope supplied while signing is not configured securely: `401`;
- valid signature for an unknown, disabled or non-public hostname: `404`;
- valid context: resolve the active `StorefrontDomain -> Storefront -> Tenant`
  relation and pass the resulting immutable `TenantScope` to the command.

Neither `tenant_id` nor `storefront_id` is accepted from public payloads. The
public `GET /api/v1/storefront/context` projection exposes slugs, branding
identity, domain, city, locale and currency, but no internal IDs.

## Proxy boundary

The browser must not know the signing secret. A non-canonical storefront sends
browser writes to a same-origin server route; that trusted route strips any
incoming `X-MVN-Storefront-*` headers, signs the API target itself and forwards
the request. Direct client-controlled headers are not authority.

The same rule applies to server-rendered catalog and configuration reads. Edge
or SSR logs must not record the secret or the complete signature envelope.
Every successfully signed API response is marked `Cache-Control: private,
no-store` and `CDN-Cache-Control: no-store`; shared caching belongs behind the
same-origin storefront runtime and must be keyed by storefront identity.

The current key is platform-wide and is suitable only for MVN-owned runtimes.
Do not distribute it to an external tenant. Before an external white-label
runtime is operated outside MVN-controlled infrastructure, replace this key
with a per-runtime credential/key ID or keep signing in one centrally managed
edge boundary.

## Rotation without downtime

1. Generate a new random secret of at least 32 bytes.
2. Deploy the API with the new value in
   `STOREFRONT_CONTEXT_SIGNING_SECRET` and the old value in
   `STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET`.
3. Switch every trusted storefront runtime to the new primary secret.
4. Verify both Lead and Order canaries and wait longer than the maximum
   signature lifetime.
5. Clear `STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET` from the API.

The previous key is accepted only while a non-empty primary key is configured.
Clearing the primary key is the fail-closed kill switch and disables signed
context even if a stale previous-key variable remains in the environment.

Never reuse `SECRET_KEY`, bot credentials or a Cloudflare token for this
contract.

## Canary gate

Before enabling traffic for a second storefront:

1. create its `Storefront` and primary active `StorefrontDomain`;
2. call `GET /api/v1/storefront/context` with a valid signed envelope and check
   the expected slug, hostname, city, locale and currency;
3. create one test Lead and one test Order through the same trusted proxy;
4. verify their persisted `tenant_id/storefront_id` pair and Manager visibility;
5. repeat each mutation with a forged signature and verify `401` with no row;
6. test rollback by removing the new domain from routing while keeping
   canonical `mvn/main` healthy.
