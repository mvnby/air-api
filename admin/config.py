from sqladmin import ModelView
from models import GlobalConfig

class GlobalConfigAdmin(ModelView, model=GlobalConfig):
    name = "Настройка"
    name_plural = "Настройки сайта"
    icon = "fa-solid fa-gears"
    
    column_list = [GlobalConfig.key, GlobalConfig.value, GlobalConfig.description]
    column_labels = {
        "key": "Ключ (код)",
        "value": "Значение",
        "description": "Описание"
    }
    
    form_columns = [GlobalConfig.key, GlobalConfig.value, GlobalConfig.description]
