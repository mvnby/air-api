# Trusted public storefront request contract

## Purpose and trust boundary

Public catalog reads, Lead creation and checkout must get their storefront from
the server runtime that served the website. Browser-provided tenant or
storefront IDs, `Origin`, `X-Forwarded-Host` and unsigned storefront headers are
never authority.

The canonical MVN website may temporarily call the ordinary API host without a
signature. A non-canonical storefront is accepted only through a complete
short-lived HMAC envelope produced by its trusted SSR or same-origin proxy.

## Required signed headers

The trusted runtime sends exactly one value for each header:

- `X-MVN-Storefront-Key-Id`: configured runtime key ID, for example
  `mvn-web-2026-08`;
- `X-MVN-Storefront-Host`: the public storefront hostname, for example
  `orsha.mvn.by`;
- `X-MVN-Storefront-Timestamp`: canonical Unix seconds (`0` or a decimal value
  with no sign, whitespace or leading zeroes);
- `X-MVN-Storefront-Signature`: `v1=<64 lowercase SHA-256 hex characters>`.

Any incomplete set, duplicate value, unknown `X-MVN-Storefront-*` header,
unknown key ID or malformed value returns `401`. The browser-facing proxy must
strip all incoming headers with that prefix before creating its own envelope.
Incomplete, duplicate and unknown sets are rejected at the outer ASGI boundary
without reading or parsing the request body.
These infrastructure credentials are deliberately omitted from the generated
OpenAPI/browser client; this document is the signing contract for trusted
server runtimes.

## Canonical v1 message

The signature is HMAC-SHA256 over these seven fields in this exact order:

```text
v1
<timestamp>
<HTTP method>
<raw path and optional raw query>
<upstream API hostname>
<storefront hostname>
<lowercase SHA-256 hex of the exact request body>
```

There is one ASCII LF byte (`0x0a`) between fields and no trailing newline.
The complete byte sequence is signed with the UTF-8 secret.

Canonicalization rules:

1. `timestamp` is canonical base-10 Unix seconds.
2. The HTTP method is uppercased as ASCII.
3. The target starts with `/`. Append `?` and the raw query bytes only when the
   query is non-empty. Do not decode, reorder or re-encode query parameters.
   The fragment is never present. CR or LF is invalid.
4. The upstream API hostname comes from the actual HTTP `Host`/`:authority`
   received by air-api. It is lowercased, converted to IDNA ASCII and stripped
   of a port and trailing dot. It must also be in
   `STOREFRONT_CONTEXT_API_HOSTS` (the production default includes
   `api.mvn.by` and loopback smoke-check hosts).
5. The storefront hostname uses the same lowercase IDNA/no-port/no-trailing-dot
   normalization.
6. Hash the exact transmitted body bytes, before JSON/form parsing. The empty
   body digest is
   `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

For a structurally complete envelope, air-api reads the exact bounded body,
checks the API host, key ID, timestamp, raw target, storefront host, digest and
HMAC, and only then calls FastAPI. The verified normalized storefront hostname
is carried inward as an immutable ASGI scope marker; route dependencies never
re-authenticate from raw headers. The body is replayed unchanged for JSON or
multipart parsing. This buffer is hard-limited by
`STOREFRONT_CONTEXT_MAX_BODY_BYTES` (20 MiB by default, matching the current API
ingress limit); an oversized signed request returns `413` without reaching the
endpoint. A valid signature with malformed JSON can therefore return `422`,
while a partial or forged envelope with the same bytes returns `401` before the
parser or database dependency runs.

Installation-estimate and repair-diagnostic attachments also enforce an
18 MiB aggregate file-content limit inside the API. This protects direct
canonical traffic that does not pass through the signed-body buffer and leaves
approximately 2 MiB for multipart boundaries and form fields under the default
20 MiB gateway envelope. Each image remains independently limited to 10 MiB.

Changing method, raw path, raw query, upstream API host, storefront host or any
body byte invalidates the signature.

## Runtime keyring and rotation

Keys exist only in runtime secret configuration:

- `STOREFRONT_CONTEXT_SIGNING_KEY_ID` and
  `STOREFRONT_CONTEXT_SIGNING_SECRET` are the primary pair;
- `STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID` and
  `STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET` are the optional rotation pair;
- every secret contains at least 32 UTF-8 bytes;
- key IDs are a case-sensitive allowlist and are never supplied by the
  database or a public payload.

The API selects one allowed key by ID and compares the HMAC in constant time.
The previous key is accepted only while a complete primary pair is configured.
Clearing the primary pair disables every signed request, including a request
using a stale previous key.

Zero-downtime rotation:

1. Add the new pair as primary and keep the old pair as previous.
2. Deploy air-api, then switch each trusted storefront runtime to the new key.
3. Run read, Lead and Order canaries with the new key.
4. Wait longer than `STOREFRONT_CONTEXT_MAX_AGE_SECONDS`.
5. Remove the previous pair.

Never reuse `SECRET_KEY`, bot credentials or a Cloudflare token.

The current primary/previous slots form one MVN-operated platform keyring: a
holder can sign for any active storefront domain. It is therefore suitable only
for runtimes controlled by MVN. Before an external tenant controls its own
runtime, introduce per-runtime credentials bound to an explicit storefront-host
allowlist or keep signing in the centrally managed MVN edge.

## Replay boundary

`STOREFRONT_CONTEXT_MAX_AGE_SECONDS` is constrained to 30–900 seconds. Requests
outside the past/future window fail closed. The body digest prevents changing a
captured request.

There is deliberately no in-memory nonce cache: it would allow replay against
another HA replica. Until a shared PostgreSQL/Redis nonce ledger is introduced,
an identical captured request can be replayed within the accepted time window.
Every public write therefore still needs its domain idempotency contract. Keep
the window short, use TLS, never log the envelope, and do not treat this HMAC as
user authentication.

## Public write idempotency

`POST /api/v1/orders` and every public Lead intake (`contact`,
`product-availability`, `installation-estimate`, and `repair-diagnostic`) use
the `Idempotency-Key` header. The accepted value is 16–128 characters from
`A-Z`, `a-z`, `0-9`, `.`, `_`, `:`, and `-`.

The API hashes the key and validated logical request content before storage.
Receipts are unique by server-resolved tenant, storefront, command, and key;
they never store the key, raw body, form fields, filenames, or other request
PII. Multipart fingerprints use normalized form fields and each attachment's
content hash, MIME type, size, field, and position. Regenerating a multipart
boundary therefore does not change the fingerprint.

The receipt and business mutation commit in one PostgreSQL transaction. A
concurrent request on another replica waits at the unique insert, then either
replays the original successful status/body or takes ownership after a failed
transaction. Reusing a key with different logical content returns `409`.

Signed storefront writes without `Idempotency-Key` return `428`. During the
canonical MVN transition only, an unsigned request accepted under
`STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=false` receives an ephemeral
server-generated key. This fallback preserves legacy availability but cannot
deduplicate a client retry. Installation estimate keeps its pre-existing rule:
the header is required even for unsigned canonical traffic. Before enabling
required signatures, `mvn-web` must
generate one key per user submission, retain it across transport retries, and
send it for checkout, contact, availability, and repair; installation estimate
already does so. Remove the unsigned fallback only together with the canonical
signed-traffic rollout.

The coordinated `mvn-web` release must also lower installation's current
30 MiB client aggregate to 18 MiB and add the same 18 MiB aggregate check to
repair. The API limit is authoritative; browser checks exist only to fail early
with a useful message.

## Resolution and compatibility

- No signing headers, an allowed ordinary API host and
  `STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=false`: resolve only canonical
  active `mvn/main`; `Host`, `Origin` or forwarded browser headers cannot select
  another storefront.
- No signing headers on an unapproved/non-API host: `401`.
- `STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=true`: every protected public
  storefront request must be signed, including canonical MVN traffic.
- Invalid, stale or forged envelope: `401`.
- Valid signature for an unknown, disabled or non-public
  `StorefrontDomain -> Storefront -> Tenant` relation: `404`.
- Valid relation: pass its immutable `TenantScope` to the public command.

For protected `/api/v1/**` routes, unsigned API-host validation and the
require-signed switch also run at the outer ASGI boundary. A wrong `Host` or an
unsigned request while the switch is enabled therefore returns `401` before
body parsing. Canonical unsigned requests remain unbuffered when the switch is
off, preserving ordinary browser CORS behavior.

Every response to a request containing any `X-MVN-Storefront-*` header is
forced to `Cache-Control: private, no-store`, `CDN-Cache-Control: no-store` and
`Vary: X-MVN-Storefront-Host`. This is applied at the final ASGI response
boundary, so it also covers rejected oversized bodies (`413`), FastAPI body
validation (`422`), route misses (`404`) and invalid/partial envelopes (`401`).
Existing `Vary` values are preserved and de-duplicated. Unhandled errors are
given the same headers explicitly by the global exception handler because
Starlette's outer error middleware creates that response outside the user
middleware chain. Shared caching belongs behind the trusted storefront runtime
and must be keyed by storefront.

The signing envelope is a server-to-server contract for trusted SSR or a
same-origin website proxy. Browsers must not receive credentials or send these
headers directly, and CORS preflight is not an authentication or signing
boundary. In air-api the signed-gateway/private-response middleware wraps CORS,
session and routing middleware; CORS behavior therefore remains unchanged while
all storefront-marked responses remain non-cacheable by shared intermediaries.

Neither `tenant_id` nor `storefront_id` is accepted from public payloads. The
public context DTO exposes only public slugs and display attributes.

## Protected public surfaces

The gateway is attached to storefront context, catalog/revision/spec/filter,
content/config/collection reads, public Lead adapters and public Order checkout.
It is not attached to Manager, internal bot, system or health/readiness
boundaries. The only intentionally open `/api/v1` routes are the exact `GET`
endpoints for EGR proxy, bank proxy, address suggestions and Yandex Business
feed; an app-level route inventory test rejects any new unclassified route.

## Production canary and rollback

Before enabling a second storefront:

1. Keep `STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=false`.
2. Configure the API primary key pair and allowed upstream API host on both HA
   runtimes; configure the same pair only in the trusted storefront server.
3. Create the second `Storefront` and active primary `StorefrontDomain` through
   the reviewed tenant setup path. Do not put test domains in migrations.
4. Call `GET /api/v1/storefront/context` through the proxy and verify its public
   identity and no-store headers.
5. Run one signed catalog query, one Lead and one Order canary. Verify exact
   persisted `tenant_id/storefront_id` and Manager visibility.
6. Tamper with query, body, host and signature; each request must return `401`
   and create no row.
7. Keep canonical unsigned `mvn.by` smoke checks green. Turn on
   `STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS` only after canonical traffic is
   also server-signed.

Rollback is configuration-first: remove second-storefront routing, disable the
require-signed switch, and clear the primary/previous key pairs if the trusted
proxy is suspected. Canonical unsigned `mvn/main` remains available while the
switch is false. No schema rollback is required.
