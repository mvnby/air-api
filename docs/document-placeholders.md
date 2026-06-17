# Document Placeholders

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
