# Users, companies and access

## Ownership and boundaries

One person has one account. Company participation is a `TenantMembership`, with
its own role, status and explicitly delegated permissions. A company may own
multiple storefronts; storefront selection never grants access to another company.

Platform authority belongs to the explicitly bound owner identity in
`LegacyOwnerAuthState.owner_staff_user_id` while staff authentication is active.
The guarded runtime owner is the platform owner in legacy mode. `is_system_tenant`
describes data ownership, not a grant of platform authority. Company owners and
administrators, including those in the system company, cannot delegate platform
authority. The legacy-owner cutover and recovery fences remain in force.

## Stage 1: explicit permissions

| Role or permission | Allowed work |
| --- | --- |
| Company owner | Company staff, CRM, company settings and documents |
| Company administrator | Ordinary employees and operational company work; cannot modify owners/admins or promote to their roles |
| Manager | Company CRM and published catalog selection; no implicit shared-catalog editing |
| Catalog editor | Shared reference workspace only when explicitly granted; no CRM access |
| `catalog.master.edit` | Shared product, brand, series, feature and tag editing |
| `catalog.master.delete` | Destructive catalog actions; requires edit permission |
| Platform owner | Platform operations and explicit catalog delegation across companies |

The platform owner manages grants at **Platform → Catalog access**
(`/manager/platform/access`). Each grant belongs to one membership and is checked
live with account/company/membership status; a copied JWT cannot create or retain
revoked permission. The directory has bounded pagination and exposes no credentials
or order data. Updates require the current membership timestamp and append an
audit event in the same transaction. Company staff CRUD cannot change these grants.

Editing references does not grant procurement, supplier filters, purchase prices,
margin, platform integrations, global media cleanup, imports or bulk-change tools.
Shared editor responses redact purchase metrics. Ordinary master retail prices
remain part of the product card. Existing-product unpublishing requires delete
permission. Product gallery editing is separate from global media-library access.

Telegram catalog price/delete commands use the same live explicit catalog grants;
legacy manager status alone cannot bypass them. Existing installer profile writes
use the staff policy and cannot reset a privileged account or disable an owner
through the contractor compatibility surface.

Staff role/status updates lock the company before employee rows and count active
owner memberships against active accounts. Concurrent demotions/disable operations
cannot remove the last active owner. Historical ownership is not rewritten.

## Release and verification

Migration `t1161access01` adds an empty JSON permissions list to memberships.
It does not grant permissions, provision accounts or merge existing identities.
The existing bound platform owner keeps access; other system-company staff lose
implicit platform/collaborative editing access and need an explicit grant.

Required evidence: focused policy/API and concurrent-owner tests, migration and
API-client checks, Manager build/component tests, green CI and deployment, then
the standard health/products/filter smoke checks. Permission grants are separate
explicit owner actions, not automatic post-deploy provisioning.

Keep the additive column during an application rollback. Old application versions
infer broader authority from system-company membership, so a rollback to the old
policy requires first restricting affected non-owner accounts. Do not downgrade
the schema while a newer application instance remains active.

## Stage 2: personal profile and Telegram

The account menu opens one personal profile at `/manager/profile`. A person can
edit their name, phone, email, photo and Telegram notification preference. Login,
company roles and catalog grants are separate controls. Profile writes require
the current profile timestamp and `X-Kitlane-Profile: 1`; stale edits return
`409/profile_changed`. Changing contact email does not create a login factor.

Photos accept JPEG, PNG or WebP up to 5 MiB and 20 million pixels. The server
rejects animation, applies orientation, crops to a square and stores only a
256px WebP without source metadata. The authenticated photo endpoint checks the
viewer company before returning bytes or a conditional `304`. Retained company
memberships allow old order photos; platform owners can inspect across companies.
Photos have private, revalidated caching and never enter the public media library.

Telegram connection uses a five-minute private-bot link. The bot proves its actual
sender; the originating browser shows that profile and must confirm it. A
forwarded link alone cannot bind a different person. A Telegram account already
bound to another person cannot be stolen or merged. The bot also supports login
for existing linked accounts through an explicit approval with a matching browser
code. It does not create an account. Browser secrets are HttpOnly and opaque
deep-link tokens are stored only as hashes. Login approval is consumed once and
rechecks account version, company access and the owner recovery fence.

Telegram link/removal rotates the authentication version and refreshes the current
browser session. Removal requires a working alternate username/password. Turning
notifications off preserves bot and login access while suppressing eligible
deliveries, including previously queued staff-task notifications.

Revoked Telegram bindings are retained in a private identity ledger. An old ID
cannot regain bot privileges or deliveries through legacy `ADMIN_IDS` after
unlinking or replacement. A later explicit verified binding remains authoritative.
The compatible signed widget also finalizes identity, membership and replay proof
under the same transaction; its JWT uses the verified authentication version.

Migrations `t1162profile01` and `t1162telegram01` are additive and do not merge
accounts. The fixed owner-profile consolidation has a separate reviewed plan and
protected production workflow. It keeps the bound owner ID, login, password,
authentication version and existing connector/business references; it transfers
the other profile's personal data and retires that identity as historical.
Authentication never follows historical aliases. See the dedicated
[consolidation procedure](owner-profile-consolidation.md).

## Stage 3: companies, sites and invitations

The company/site selectors use the live account bootstrap and explicit scoped
request headers. A person's roles are evaluated in the selected membership;
roles from another company are never combined. The platform owner can support
active partners without accumulating owner memberships. Personal profile,
Telegram and password settings continue to use the actual personal membership.
See the [selection contract](manager-storefront-selector-contract.md).

**Companies and sites** gives the platform owner a paginated directory of all
partners, including disabled/demo companies, their owners, active staff counts,
sites and domain states. The owner can change a company name and enable/disable
it with an optimistic timestamp and an atomic audit. The canonical system company
cannot be disabled. Disabling blocks fresh company requests; it does not delete
data or remove already cached public pages. Site/domain entries are read-only:
there is no implicit DNS change, provisioning or catalog grant.

Company owners/admins see their own sites, including draft/disabled sites, and
manage staff through invitations. An invitation is a single-use link valid for
seven days, stored only as a token hash. The owner copies and delivers it; creating
one does not send a message. Previewing it does not join the company. Acceptance
requires a new person's chosen login/password or an existing person's live
session/explicit credentials; email matching never attaches an account.

Acceptance rechecks the inviter's current authority and allowed role, company
status and recipient identity under transaction locks. Revoked, expired, consumed
or stale-authority invitations cannot grant access. No invitation upgrades an
existing membership or adds shared-catalog permissions. Blocked and merged
identities cannot accept. An inactive person with every former membership disabled
can return only with the correct existing password and a valid invitation; the
authentication version rotates and former memberships/grants remain disabled.

Shared installer/rate settings are still global legacy fields. A worker with
those settings cannot join a second company until membership-specific worker
settings are implemented. The bound platform owner similarly retains one actual
canonical membership and uses support contexts elsewhere.

The staff bot keeps its own selected company/site and a monotonic context version.
Only actual active memberships are available in the bot; virtual operator support
is web-only. Business operations check the issued context version, fresh company,
membership role and site; switching invalidates old action buttons and drafts.
Slow OCR/voice work rechecks the captured context before persistence. Notifications
check access in the event's own company/site independently of the bot selection.
Personal Telegram linking/login and the single polling lease remain separate.

Migrations `t1164team01` and `t1164bot01` add invitations and bot selection without
provisioning memberships or changing existing assignments. Release the compatible
standalone bot first, then the API/Manager release; check the live bot contract
and polling lease after both releases. Required proof includes company isolation,
invite consumption/revocation and concurrent acceptance, stale bot actions,
Manager bootstrap/unsaved navigation, migration/client checks and normal smoke
checks. Keep additive tables during rollback; do not activate multi-company work
through an older API with ambiguous membership resolution.

## Subsequent authorized stage

1. **Order responsibility:** a responsible sales manager, avatar/name in lists
   and kanban, personal filtering and audited reassignment; work-stage executors
   remain separate assignments.

Installer workspaces, collection instructions and supplier-only accounts remain
later releases. Catalog and CRM have separate permission boundaries now; deploying
them as independent applications is a future architecture decision.

Related procedures: [authentication](api/authentication.md),
[Git workflow](git-workflow.md), [production data operations](production-data-operations.md)
and [bot ownership](bot-service-boundary.md).
