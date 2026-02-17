from sqladmin import ModelView
from models import GlobalConfig

from admin.view_constants import (
    GLOBAL_CONFIG_COLUMN_LABELS,
    GLOBAL_CONFIG_ICON,
    GLOBAL_CONFIG_NAME,
    GLOBAL_CONFIG_NAME_PLURAL,
)


class GlobalConfigAdmin(ModelView, model=GlobalConfig):
    name = GLOBAL_CONFIG_NAME
    name_plural = GLOBAL_CONFIG_NAME_PLURAL
    icon = GLOBAL_CONFIG_ICON

    column_list = [GlobalConfig.key, GlobalConfig.value, GlobalConfig.description]
    column_labels = GLOBAL_CONFIG_COLUMN_LABELS

    form_columns = [GlobalConfig.key, GlobalConfig.value, GlobalConfig.description]
