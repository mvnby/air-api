# ZAPRO.SU for platform AI

This connection belongs to the system platform. A partner owner cannot read,
change, test, or spend its key. It does not change existing DeepSeek workflows,
OCR, the Telegram bot, storefront requests, or the models used by Codex agents.

## Enter the key in Manager

1. Create a ZAPRO.SU API key in [API Keys](https://po.zapro.su/docs/api/)
   with group `AUTO`. Keep the key outside chat and screenshots.
2. Sign in as a system platform owner or admin. Open **Manager → Настройки →
   AI-подключение**.
3. Paste the key into **API-ключ** and click **Сохранить**. The field clears after
   saving; an empty field on later saves keeps the existing key. No plaintext
   or mask is returned by the API.
4. Click **Проверить подключение и получить модели**. This reads `/v1/models`
   and confirms catalog access only. It does not prove text, tools, JSON mode,
   or a specific model's availability for inference.
5. Select an ID from the returned list, save, and, if desired, click
   **Проверить текстовый запрос**. This deliberately sends only a short synthetic
   prompt with a 16-token limit and may consume a small amount of balance.
6. Click **Включить** to permit explicit trusted backend call sites to use the
   selected model. Click **Отключить** to stop them, or **Удалить ключ** to remove
   the credential and configuration.

The user key is stored only in `platform_ai_connection` using the shared
`INTEGRATION_CREDENTIAL_KEYRING_JSON` keyring and a domain-specific context. It
is included in integration credential health checks and the reviewed rewrap
plan. The Manager entry is the only implemented key source; `ZAPROSU_KEY` from
the provider's example is **not** read by this application. No production
credential rotation is part of this change.

## Backend contract

`PlatformAIConnectionService.complete(...)` is the reusable, explicit opt-in
entry point for trusted platform code. It requires an enabled connection and a
selected model. The initial Manager inference check is the only new caller;
existing product AI scenarios continue through DeepSeek. Partner endpoints must
not call this method or gain a fallback to the platform balance.

The transport uses the fixed `https://po.zapro.su/v1` host, Chat Completions
only, no redirects or environment proxy, and bounded response bytes, request
time, output tokens, and concurrent calls. It does not send DeepSeek-specific
thinking, temperature, or JSON-format options. A model that lacks Chat
Completions returns an explicit rejection. There is no automatic model
fallback. Technical usage tokens and returned model are exposed by the explicit
test; cost and remaining balance are not inferred.

After deployment, enter the real key through Manager and run the catalog check
and optional synthetic inference check there. Development and CI use mocks;
without a user key, live provider access remains unverified.
