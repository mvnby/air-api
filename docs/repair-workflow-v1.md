# Repair Workflow V1 Decision Note

## Selected Issues

- #314: service tariff directions, repair direction, manager tariff UI cleanup.
- #329: discovery only for repair workflow and defect report document.

## Sprint Goal

Prepare the service pricing foundation for repair work without implementing the full repair workflow yet. Managers should be able to maintain repair tariffs separately from installation, dismantling, and maintenance tariffs. The next implementation slice can then build repair orders, repair documents, and defect reports on top of this direction.

## Repair V1 Scope

- Add repair as a first-class service tariff direction.
- Keep repair estimates based on base tariff plus selectable/manual rules.
- Do not use route-specific fields for repair tariffs.
- Reuse the existing service estimate snapshot flow for repair pricing where possible.
- Define a defect report document model before implementation.

## Defect Report V1

The defect report should be a separate order document type for repair workflows. It should be template-driven like contracts and invoices.

Suggested fields:

- Equipment type and model.
- Serial number.
- Inventory number.
- Object address.
- Customer representative.
- Inspection date.
- External condition.
- Detected defects.
- Technical conclusion.
- Recommended decision: repair, replacement, write-off, additional diagnostics.
- Estimated materials and parts.
- Photos or references to order media, if available.

Suggested defect library groups:

- Wear and contamination: high wear, clogged heat exchanger, dirty filters, damaged insulation.
- Refrigeration circuit: refrigerant leak, low refrigerant, compressor failure, capillary/valve blockage.
- Electrical: damaged wiring, control board failure, sensor failure, fan motor failure.
- Installation defects: incorrect route, poor drainage, vibration, missing service clearance.
- Economic decision: repair is not cost-effective, spare parts unavailable, replacement recommended.

## Out Of Scope

- Full repair statuses and lifecycle.
- Technician mobile flow.
- Automatic creation of a defect report from diagnostics.
- Inventory/spare-parts accounting.
- Warranty decision automation.
- Separate Google Docs templates for every repair subtype.

## Verification Scenarios

- A manager can create a repair tariff.
- Repair tariffs do not show route meters in the manager tariff UI.
- Repair tariff quick-add suggestions do not append installation route wording.
- A repair estimate can be calculated from base price plus generic repair rules.
- Existing installation tariff behavior with route and holes remains unchanged.

## Risks And Dependencies

- #329 should start from a narrow vertical slice: repair order fields, repair status set, one defect report template, and one generated PDF.
- The defect report needs a small structured data model before UI work, otherwise templates will depend on free text too heavily.
- #314 and #329 touch the same service estimate concepts, so repair document work should avoid changing installation estimate behavior in the same PR.
