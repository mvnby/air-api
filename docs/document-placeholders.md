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
