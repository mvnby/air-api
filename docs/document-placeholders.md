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
