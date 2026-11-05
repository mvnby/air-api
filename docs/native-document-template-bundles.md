# Native document template bundles

Template bundles solve first-run onboarding without putting tenant-owned DOCX
files, logos, seals, or signatures into Git. Git contains only a reviewed
manifest with metadata and SHA-256 checksums. The DOCX files are supplied from
a private directory and written directly to the tenant's private template
storage.

## Safe workflow

1. Put every DOCX named by the manifest into a private source directory.
2. Run the read-only plan. It validates every checksum and DOCX placeholder
   contract before reading or changing database state:

   ```bash
   python3 scripts/manage_native_document_template_bundle.py plan \
     --manifest config/native_document_template_bundles/mvn-2026-v1.json \
     --source-dir /private/path/to/templates \
     --tenant-id 1 \
     --legal-entity-id 1
   ```

3. Review the plan. Apply requires the exact bundle id:

   ```bash
   python3 scripts/manage_native_document_template_bundle.py apply \
     --manifest config/native_document_template_bundles/mvn-2026-v1.json \
     --source-dir /private/path/to/templates \
     --tenant-id 1 \
     --legal-entity-id 1 \
     --confirm-bundle-id mvn-2026-v1
   ```

The command is idempotent: it reuses a canonical name or declared alias,
updates scenario metadata, and uploads a version only when the active SHA-256
differs. It never deletes a template or historical version.

Only one apply for the same tenant and seller can run at a time on
PostgreSQL; a second operator gets a clear refusal instead of duplicate cards.
Database rows and private object storage cannot share one transaction, so a
storage or database failure may stop after some templates were activated. The
error names the failed key. Fix the cause and repeat the exact same apply: the
idempotent plan skips every already matching version and resumes the remainder.
Always finish by running `plan` again; every action must be `keep`.

## Partner onboarding

Partners do not need a Google Cloud project for native generation. Create their
seller legal entity, upload or import their own DOCX versions, and configure
official numbering. A Google account is required only when they explicitly
choose the separate legacy Google mode.

Electronic invoices and electronic waybills are outside this bundle. The
current TN-2/TTN-1 path produces printable files only; ESF/EDI integration stays
deferred until a tenant actually needs it.

## Печать ТН-2 и ТТН-1 на бланках MVN BY

Пакет `mvn-paper-waybills-v1` содержит две редактируемые формы для основного
продавца MVN BY без НДС. Исходники собираются из обезличенной геометрии
печатных вкладок. Книжный A4, поля слева/справа 18/9 мм, сверху 12,5 мм,
снизу 16,03 мм. Верхняя часть отведена под типографскую шапку. Серия и номер
учтённого бумажного бланка находятся на самой бумаге. Учётный номер CRM остаётся
в карточке выпущенного документа.

Внутри товарной секции форма печатает таблицу. Высота строки растёт с названием
и страной происхождения. Итог и поля ниже сдвигаются вслед за фактическими
строками. Предпросмотр показывает все строки. При выпуске этой версии Manager проверяет, что
финальный PDF занимает один книжный A4. При переполнении черновик можно
исправить или выбрать другую форму. Согласуйте дальнейшее оформление с
ответственным за бланки. Служебные комментарии,
расчётные листы, предыдущие номера, сведения о людях и подписи из эталонов в
пакет не входят. Незаполненные служебные реквизиты допускают вписывание вручную.

1. В приватном рабочем каталоге подготовьте DOCX и сравните полученный manifest
   с версионированным. Обработка выполняется без доступа к Google. Используйте
   версии библиотек из проекта.

   ```bash
   python3 scripts/prepare_mvn_waybill_templates.py --output-dir /private/waybill-sources \
     --manifest /private/waybill-sources/manifest.json
   diff -u config/native_document_template_bundles/mvn-paper-waybills-v1.json /private/waybill-sources/manifest.json
   ```

   Для сверки сетки с собственными XLSX-экспортами можно передать каталог
   `--extract-grid-from` с файлами `tn2.xlsx` и `ttn1.xlsx`. Проверяются
   печатные вкладки «ТН-2» и «ТТН-1», ориентация и поля, размеры строк и
   столбцов. Хранятся только числа. После такого изменения повторите приёмку
   макета на бумаге и сравните новые контрольные суммы.

2. Выполните описанный выше `plan` для manifest
   `config/native_document_template_bundles/mvn-paper-waybills-v1.json`,
   приватного каталога исходников и целевых идентификаторов. Команда проверяет
   компанию, активного основного продавца и его налоговый режим. Применение
   пакета на рабочем сервере проходит отдельно по правилам
   [операций с рабочими данными](production-data-operations.md). После
   утверждённого применения повторите `plan` и проверьте действия `keep`.

3. В Manager откройте заказ → «Документы» → «DOCX · В CRM», выберите ТН-2 или
   ТТН-1, нужное предложение и документ-основание. В «Шаблон и реквизиты»
   выберите «ТН-2 · печать на бланке» либо «ТТН-1 · печать на бланке».
   Собственный шаблон выбирается здесь же. В ТТН-1 проверьте автомобиль,
   водителя, маршрут, операции и отдельно УНП плательщика, если он известен.
   В черновике проверьте грузовые места и массу.

4. Проверьте PDF с тем же составом и количеством строк. Для первого совмещения
   напечатайте синтетическую пробу на обычном листе A4 в масштабе 100 %, без
   «вписать в страницу», и приложите к своему бланку на просвет. Сверьте
   дату, УНП, начало товаров и итог. После совпадения используйте тот же
   принтер, лоток и настройки. Пробная печать не расходует учтённый бланк.
