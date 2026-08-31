# Document Placeholders

## Native DOCX templates

The Manager document system is the primary path for new templates. A DOCX can
contain scalar placeholders such as `{{ document.official_full_number }}`, safe
conditional blocks such as `{{#if customer.organization_statutory_body}}`, and
repeatable table anchors such as `{{ lines }}`. The authoritative, current
catalog is available in **Settings → Documents → DOCX templates** and through
`GET /api/manager/document-system/placeholder-catalog`; do not maintain a
second hand-written field list in this file.

Templates are owned by one tenant and one seller legal entity. Uploading a
changed Word file creates an immutable draft version. Activating it retires the
previous active version without modifying documents that were already issued.

Contract template cards can be bound to one of the seven contract scenarios.
Invoice cards can be bound to either a payment request or an invoice-offer.
The order workspace then offers the matching template automatically, while an
unbound template remains a universal fallback.

Warranty months are frozen in the draft snapshot. Seller defaults prefill the
form; equipment defaults to 36 months when no value is configured. A value of
`0` explicitly means “do not include a contractual warranty block” (it does
not alter any mandatory statutory rights).

The native snapshot stores seller and customer party types independently.
Use the party conditions instead of writing one fixed preamble:

- `seller.individual_entrepreneur_self` / `customer.individual_entrepreneur_self`
- `seller.organization_statutory_body` / `customer.organization_statutory_body`
- `seller.signs_by_power_of_attorney` / `customer.signs_by_power_of_attorney`

For printable TN-2/TTN-1 templates, transport values are available as
`transport.car_model`, `transport.car_number`, `transport.driver_name`, and
`transport.carrier`. This does not submit an electronic waybill to EDI.

## Legacy Google templates

The sections below document the compatibility placeholders used by the legacy
Google Docs/Sheets generator. Legacy mode remains optional and separate from
the native versioned DOCX workflow.

## Object Address

Use `{{object_address}}` in document templates when the act or another document needs the work site address.

The value is resolved from the order address first, then from the selected customer branch address. If neither is filled, the generator inserts an empty string.

## Contract Party Roles

Templates for acts and invoices may keep normal Russian role words:

- `продавец`
- `покупатель`

For acts and invoices only, the generator can replace these words and their common case forms according to the selected role type:

- `seller_buyer`: no replacement
- `executor_customer`: продавец -> исполнитель, покупатель -> заказчик
- `contractor_customer`: продавец -> подрядчик, покупатель -> заказчик

The role type can come from the contract template default, the open customer contract, or the order override.

## Base Document

Closing document templates for acts, ТН-2 and ТТН-1 can use a neutral base document reference:

- `{{base_document_type}}`
- `{{base_document_number}}`
- `{{base_document_date}}`

When the selected base document is an invoice, `{{invoice_number}}` and `{{invoice_date}}` are also populated. When it is a one-time order contract, `{{contract_number}}` and `{{contract_date}}` use that document.

For B2C templates (`retail_receipt`, `service_act`) the base document is populated as the public offer:

- `{{offer_url}}`
- `{{base_document_type}}`
- `{{base_document_number}}`
- `{{base_document_date}}`
- `{{date_text}}`
- `{{date_day}}`
- `{{date_month}}`
- `{{date_year}}`

## B2C Documents

Product receipt templates can use:

- `{{receipt_product_lines}}`
- `{{receipt_product_qty}}`
- `{{receipt_product_price}}`
- `{{receipt_product_total}}`
- `{{receipt_service_lines}}`
- `{{receipt_service_qty}}`
- `{{receipt_service_price}}`
- `{{receipt_service_total}}`
- `{{receipt_total}}`
- `{{receipt_total_in_words}}`

Service act templates can use:

- `{{equipment_primary}}`
- `{{equipment_list}}`
- `{{service_act_lines}}`
- `{{service_act_total}}`
- `{{service_act_total_in_words}}`

## Additional Conditions

Use `{{additional_conditions}}` in contract templates for order-specific terms. The value comes from the manager order document block.
Multiple filled lines are inserted with line breaks and without manual numbering. If the placeholder is placed in a numbered Google Docs paragraph, Google Docs continues the contract numbering for every line.

To hide the whole numbered paragraph when the field is empty, put the conditional block on its own numbered paragraph:

```text
6.5 Во всем остальном стороны руководствуются законодательством Республики Беларусь.
{{#if additional_conditions}}{{additional_conditions}}{{/if}}
7. Юридические адреса и реквизиты сторон.
```

In the Google Docs template the second line should be one numbered-list item after `6.5`. When conditions are filled, they become `6.6`, `6.7`, and so on. When conditions are empty, the whole line is removed and no empty numbered item remains.
