"""Small server-rendered connection screen; authorization stays in the service."""

import html

SCOPE_LABELS = {
    "kitlane:read": ("Просмотр данных компании", "Каталог, клиенты, заказы и доступные вам поручения."),
    "kitlane:incoming:write": ("Обращения", "Сохранять и исправлять входящие обращения."),
    "kitlane:tasks:write": ("Поручения", "Создавать, изменять и завершать ваши поручения."),
    "kitlane:maintenance:write": ("Техническое обслуживание", "Сохранять замечания и фото, готовить черновики актов и предложений."),
    "kitlane:catalog:write": ("Подбор и документы", "Сохранять варианты оборудования и готовить черновики КП и счетов."),
    "kitlane:mail:read": ("Чтение почты", "Просматривать письма, черновики и вложения вашей компании."),
    "kitlane:mail:drafts:write": ("Почтовые черновики", "Создавать, изменять и удалять черновики и их вложения. Это не разрешает отправку."),
    "kitlane:mail:send": ("Отправка писем", "Отправлять только сохранённую версию, отдельно подтверждённую вами в Manager."),
}


def consent_page(*, user_name, company_name, storefront_name, pending, nonce):
    esc = html.escape
    permissions = []
    for scope, (label, description) in SCOPE_LABELS.items():
        if scope not in pending.scopes:
            continue
        if scope == "kitlane:read":
            control = '<input type="checkbox" checked disabled aria-label="Просмотр данных компании обязателен">'
        else:
            checked = "" if scope == "kitlane:mail:send" else " checked"
            control = f'<input type="checkbox" name="scope:{esc(scope, quote=True)}" value="allow"{checked}>'
        permissions.append(f'<label class="permission">{control}<span><strong>{esc(label)}</strong><small>{esc(description)}</small></span></label>')
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Подключить Kitlane к ChatGPT</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f6f8;color:#17212b;font:16px/1.5 system-ui,sans-serif}}main{{max-width:640px;margin:32px auto;padding:24px;background:white;border:1px solid #e1e5eb;border-radius:16px}}h1{{font-size:25px;margin:0 0 8px}}h2{{font-size:18px;margin:24px 0 8px}}p{{margin:8px 0}}.muted,small{{color:#596574}}.company{{background:#f3f6fa;border-radius:10px;padding:16px;margin:20px 0}}.permission{{display:flex;gap:12px;padding:12px 0;border-bottom:1px solid #edf0f4;cursor:pointer}}input[type=checkbox]{{width:20px;height:20px;flex-shrink:0;margin-top:3px;accent-color:#2459ce}}small{{display:block;margin-top:3px}}.buttons{{display:flex;gap:12px;flex-wrap:wrap;margin-top:24px}}button{{font:inherit;cursor:pointer;border:1px solid #ccd3de;border-radius:9px;padding:11px 18px;background:white}}button.primary{{background:#2459ce;color:white;border-color:#2459ce}}a{{color:#2459ce}}@media(max-width:680px){{main{{margin:0;min-height:100vh;border:0;border-radius:0;padding:24px 18px}}}}
</style></head><body><main>
<h1>Подключить Kitlane к ChatGPT</h1>
<p class="muted">Выберите, что ChatGPT сможет делать от вашего имени.</p>
<section class="company" aria-label="Ваша компания"><strong>{esc(company_name)}</strong>
<p>Пользователь: {esc(user_name)}</p><p class="muted">Филиал: {esc(storefront_name)}</p>
<small>Компания определена по вашей учётной записи. Данные других компаний недоступны.</small></section>
<form method="post" action="/api/connector/oauth/authorize">
<input type="hidden" name="consent_id" value="{esc(pending.id, quote=True)}">
<input type="hidden" name="csrf_token" value="{esc(nonce, quote=True)}">
<input type="hidden" name="scope_selection" value="explicit">
<h2>Разрешения</h2>{''.join(permissions)}
<p><small>Можно снять необязательные разрешения. Новые возможности потребуют отдельного согласия.</small></p>
<p><small>Доступ действует 30 дней. Отключить его можно в Manager → Профиль → Подключения ChatGPT.</small></p>
<div class="buttons"><button class="primary" name="decision" value="allow">Подключить Kitlane</button><button name="decision" value="deny">Отмена</button></div>
</form><p><small>Не ваша компания? Войдите под своей учётной записью в <a href="/manager/profile">Manager</a> и начните подключение заново из ChatGPT.</small></p>
</main></body></html>'''
