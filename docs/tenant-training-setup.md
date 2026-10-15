# Private teaching cabinet

This operation creates the new `training-kitlane` tenant for recording lessons.
It never adopts or changes `test1`, `polotsk`, or the operator tenant. The fixed
name is `[ОБУЧЕНИЕ] Учебная компания Kitlane`. Unlike the shared read-only demo,
its CRM remains editable.

The exact reserved identity `training-kitlane` uses the existing synthetic
catalog cost projection (90% of recommended retail price, with the normal retail
fallback). This applies to selection rows, filters/sorting and order snapshots;
real supplier purchase costs are not shown while recording. It does not enable
the read-only demo flag. Other partner slugs, including similarly prefixed
names, retain their normal cost policy.

## Exact scope

`scripts/bootstrap_private_training.py` creates one non-system active independent
seller, its active default `main` storefront, one system-owned active grant,
exactly two materialized offers, one synthetic
seller legal entity, two synthetic customers (company and individual), one new
incoming lead, and two negotiation orders. Each order has two draft alternative
proposals and exactly one selected proposal; all four product lines have
positive target retail prices and zero purchase/installation costs. Orders have
a reminder to register customer contract `УЧ-001` dated on the recording day.
The contract itself is left for the lesson.

All customer names and addresses carry `[ОБУЧЕНИЕ]`; email addresses use
`example.invalid`, customer phones contain non-routable text and the incoming
lead phone is empty. No customer/issuer has an invented registry-verified UNP,
bank account, signature or seal. Dates are created at setup time, with no stale
fixed follow-up reminders. A real public registry lookup can be demonstrated
separately during rehearsal; this fixture never claims fictional details were
verified.

The two product IDs are an explicit finite allowlist. The plan resolves their
current public `Product.price` values and requires published
`complete_split_system` products that also pass the current selection admission
rule, including its contradictory component/multisplit metadata vetoes. The
eligible IDs are included in the reviewed plan digest. It never copies CRM
records or supplier costs.
The initial reviewed candidates were `33` (MDV INFINI Loft ERP 09) and `39` (TCL
Ocarina T Pro 12); verify their current identities and prices in the fresh plan.
The existing grant schema supports policy mode `all_published` with
`inherit_master` prices. This bootstrap materializes only the two reviewed
products and runs no catalog sync. Current access still requires an exact
materialized offer. This is not a permanent finite entitlement: a later
sanctioned catalog sync would expand the grant and requires a separate reviewed
operation. Never run that sync as part of teaching setup. Linked offers make
both reviewed models available to the existing selection workflow.

There are no domain rows, DNS changes, website deployments, staff
accounts, business documents, SMS, mail, Telegram messages, notifications or
outbox events in this bootstrap.

## Reviewed production sequence

Read [production data operations](production-data-operations.md),
[deployment](deployment.md), [API HA](api-ha-runbook.md), and
[the quorum procedure](postgres-quorum-runbook.md). After the exact CI-tested
immutable image is deployed to both nodes and all required smoke checks pass:

1. Prove healthy quorum and exactly one writable primary. Resolve and pin its
   exact active immutable app container. Hold the normal per-project deployment
   lock for the plan/execute window; stop on topology/runtime changes or overlap.
2. Run the read-only plan in that image:

   ```sh
   python3 scripts/bootstrap_private_training.py plan --product-id 33 --product-id 39
   ```

3. Review `tenant_slug`, `chosen_products`, `planned_records`, `remaining_readiness`,
   `blockers=[]`, and the exact digest. Run only that fresh plan's emitted
   `reviewed_execute_command`. Its signed token expires after 15 minutes; a
   changed price, publication/type, product identity or target state requires a
   new plan. The caller commits all new DB rows and both audit receipts in one
   transaction. It has no cleanup or reset action.
4. Save the returned `target.tenant_id`, `target.storefront_id`,
   `target.legal_entity_id` and `records` IDs in the private operator report.
   Repeat the read-only plan: require `status=already_created`, the same target
   and no blockers. IDs are allocated live and must not be guessed from examples.
5. Provision a private owner through
   [the existing tenant-manager workflow](tenant-manager-provisioning.md): tenant
   slug `training-kitlane`, storefront slug `main`, display name
   `Учебный владелец Kitlane`, username `training.kitlane`, empty phone, role
   `owner`, and `reset_password=false`. Review that separate plan. Transfer the
   password privately and immediately remove the temporary GitHub secret. This
   fixture never creates or exposes credentials.

An intact replay preserves lesson edits to customer names, order statuses,
selected proposals and product lines. Existing unrelated sandbox CRM data does
not block the separate additive `scripts/setup_tenant_training.py` helper.
Missing tracked rows/receipts or conflicting targets stop; there is no automatic
repair, deletion or reset. The shared demo policy cannot be turned off by either
script. No public domain is created even though Manager requires an active
default storefront.

## Native teaching templates

The bootstrap creates a synthetic issuer, but native DOCX templates are a
separate readiness gate. Never attach another tenant's template IDs or copy its
issuer, signature, logo, seal or banking details.

The pure local preparer creates three new sources (КП, счёт, договор) with
`УЧЕБНЫЙ ОБРАЗЕЦ` permanently in their text. They show only the selected order
lines and synthetic parties, have no banking details or signing images, and
make no claim of legal completeness. The manifest is versioned at
`config/native_document_template_bundles/kitlane-training-v1.json`; DOCX bytes
are generated outside Git. ZIP metadata and document properties are fixed so
the source checksums are reproducible. Existing changed files are never silently
overwritten.

```sh
python3 scripts/prepare_training_document_templates.py \
  --output-dir /private/path/kitlane-training-v1
```

Compare all three reported SHA-256 values with the committed manifest. Use
[the sanctioned native bundle procedure](native-document-template-bundles.md),
with the actual returned IDs and that same private source directory:

```sh
python3 scripts/manage_native_document_template_bundle.py plan \
  --manifest config/native_document_template_bundles/kitlane-training-v1.json \
  --source-dir /private/path/kitlane-training-v1 \
  --tenant-id <returned-training-tenant-id> \
  --legal-entity-id <returned-training-issuer-id>
```

Review the exact three create/upload actions, then use the same arguments with
`apply --confirm-bundle-id kitlane-training-v1` under the production operation
gates. This imports template sources only, without generating, sending or
replacing business documents. Re-run `plan` and require three `keep` actions.
The existing importer resumes safely if storage/DB activation stops partway;
it never deletes previous versions. Configure or verify teaching-only document
numbering before finalization. Template source layout is visually checked in
development; rehearse actual document preview after import before recording.

## Recording readiness

Verify in a fresh private-owner login that only the new tenant/storefront is
available. Record the assigned customer, lead, order, proposal and issuer IDs.
Confirm the new incoming lead is awaiting processing; both negotiation orders
show editable alternatives, positive prices, and no real recipient contacts.
The equipment reader must show both allowlisted models and their details.

Confirm the three active native template versions belong to the new tenant and
issuer. Rehearse a preview with the selected proposal and check that only its
rows and the permanent training marker appear. For the company contract, choose
the normal `Поставка оборудования` scenario and a complete payment schedule
(for example, 100% before supply); the ordinary contract preflight still requires
these business terms. No fake tax/bank details are required by these teaching
templates, which use only the client's existing full name. During the recording, use the
company customer's Contracts tab to register `УЧ-001` dated on that day, select
a proposal and show the appropriate status change. Existing documents in any
other tenant must never be deleted or regenerated as part of this setup.

The cabinet is ready to record only after staff login, scoped reader, contract
registration and native preview have actually been verified. `already_created`
proves idempotent setup; it does not claim those later readiness gates passed.

## Optional live registry lookup for a lesson

Open **Клиенты → Новый клиент → Юрлицо → УНП**. Enter a real number confirmed
for that recording (candidate `100325912` for a Belarusbank example), then move
focus out of the field. The form requests the registry and fills the returned
full name/address; show those details only after an actual successful response
confirms the company. A failed/unavailable response is not verification.
Close the new-client form without saving after this lookup demonstration. The
synthetic teaching company and its fictional requisites remain the CRM lesson
data; neither the real organization nor an alleged nine-nines registry result
is pre-seeded.
