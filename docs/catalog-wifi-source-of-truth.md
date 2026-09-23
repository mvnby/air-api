# Wi-Fi: характеристика товара как источник статуса

## Решение владельца каталога

23 сентября 2026 года владелец каталога подтвердил статус для 13 комплектов MDV
из [аудита прайса](catalog-mdv-price-audit.md) и для пяти отдельных внутренних
блоков iERA INVERTER. Для отображения в текущем каталоге «модуль в комплекте»
считается `builtin`; модуль, покупаемый отдельно, — `ready`. Это решение о
статусе товара, а не о физической интеграции модуля. Учёт аксессуара и
совместимости серий описан в [issue #1023](https://github.com/mvnby/air-api/issues/1023).

Точный список ID, кодов моделей, прежних значений и строк листа
[MDV RAC](https://docs.google.com/spreadsheets/d/1oQIe3HonJQbTek7NTINg0x1eslNrJ6m_YaiOxRTD7-8/edit#gid=1627478535)
сохранён в
[`config/catalog_repairs/mdv_wifi_confirmed_2026_09_23.json`](../config/catalog_repairs/mdv_wifi_confirmed_2026_09_23.json).
Итог: 13 `builtin` и 5 `ready`. CLASSIC 18/24 и UVpro 18/24 уже имеют `ready`
и повторно не меняются. Карточки iERA 902–904, 1055/1056 остаются отдельными
внутренними блоками: операция не меняет их вид, состав комплекта или цену.

## Причина расхождений

Старые продуктовые теги `wifi-builtin` и `wifi-ready` были источником
нормализации поверх характеристик. В проверенном производственном снимке
641 товар имел такую связь. У 340 из них `wifi_state` ещё отсутствовал, но
`wifi_ready` уже содержал однозначное значение. У восьми MDV тег `wifi-ready`
противоречил `wifi_state=none`; эти товары входят в точечный план владельца.

Теперь `services/spec_normalizer.py`, импорт и сохранение товара берут Wi-Fi
только из `specs`. Публичные фильтры и старые значения `tag_slugs=wifi-*`
также читают характеристику. Похожие slugs в библиотеке `Feature` являются
отдельными сущностями и не удаляются.

## Порядок применения

Следовать [правилам производственных операций](production-data-operations.md)
и [runbook топологии PostgreSQL](postgres-quorum-runbook.md). После зелёного CI,
merge и успешного deploy на обоих API-узлах:

1. Проверить один и тот же активный образ, роли primary/replica и доступность
   БД. На обоих узлах запустить read-only
   `python3 scripts/repair_catalog_user_wifi.py`. Сверить 18 ID,
   `wifi_states` и один `plan_digest`.
2. На подтверждённом primary под deploy lock выполнить
   `python3 scripts/repair_catalog_user_wifi.py --execute-plan-digest <digest>`.
   Повторный план должен показать `changed=0`.
3. На обоих узлах запустить read-only
   `python3 scripts/retire_catalog_wifi_tags.py`. План должен охватить только
   два старых продуктовых тега и их проверенные связи. Он откажет при
   неподтверждённом противоречии между тегом и характеристикой. Сверить
   `removed_links`, `spec_updates`, `confirmed_tag_conflict_ids` и digest.
4. На primary под deploy lock выполнить
   `python3 scripts/retire_catalog_wifi_tags.py --execute-plan-digest <digest>`.
   Повторный план: `removed_links=0`, `deleted_tags=0`, `spec_updates=0`.
5. Проверить отсутствие продуктовых тегов `wifi-builtin`/`wifi-ready`, выборку
   Manager по `builtin`/`ready`, публичный `has_wifi`, старый фильтр
   `tag_slugs=wifi-*`, затем `/api/health`, `/api/ready`,
   `/api/v1/products?limit=5`, `/api/v1/filters/config`.

Обе команды по умолчанию read-only, требуют точного digest для записи и
отказывают на реплике. Не запускать общий `normalize_legacy.py` ради этого
исправления: он может затронуть характеристики за пределами плана.
