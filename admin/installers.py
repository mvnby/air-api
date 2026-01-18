from sqladmin import ModelView
from models import Installer

class InstallerAdmin(ModelView, model=Installer):
    name = "Монтажник"
    name_plural = "Монтажники"
    icon = "fa-solid fa-users-gear"
    
    column_list = [Installer.id, Installer.name, "telegram_id", Installer.is_active]
    column_labels = {
        "name": "Имя",
        "telegram_id": "Telegram ID",
        "is_active": "Активен",
        "default_rate": "Ставка (по умолч.)"
    }
    
    form_columns = ["name", "telegram_id", "default_rate", "is_active"]
