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

## Subsequent authorized stages

1. **Unified profile:** reconcile the existing owner identities after a reviewed
   relationship report; preserve historic audit/installer references and prove
   recovery. Add avatars, personal settings and verified Telegram linking/login
   without manual IDs. Authentication and bot messaging consent remain distinct.
2. **Company and team administration:** invitations, account participation,
   explicit multi-company request context, partner/storefront overview and
   tenant-aware bot access. Move company-specific worker settings out of the
   shared personal identity before enabling shared workers across companies.
3. **Order responsibility:** a responsible sales manager, avatar/name in lists
   and kanban, personal filtering and audited reassignment; work-stage executors
   remain separate assignments.

Installer workspaces, collection instructions and supplier-only accounts remain
later releases. Catalog and CRM have separate permission boundaries now; deploying
them as independent applications is a future architecture decision.

Related procedures: [authentication](api/authentication.md),
[Git workflow](git-workflow.md), [production data operations](production-data-operations.md)
and [bot ownership](bot-service-boundary.md).
