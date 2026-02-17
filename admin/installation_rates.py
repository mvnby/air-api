from sqladmin import ModelView

from models import InstallationRate


class InstallationRateAdmin(ModelView, model=InstallationRate):
    name = "Тариф на монтаж"
    name_plural = "Тарифы на монтаж"
    icon = "fa-solid fa-screwdriver-wrench"

    column_list = [
        InstallationRate.category,
        InstallationRate.power_range,
        InstallationRate.base_price,
        InstallationRate.extra_pipe_price,
        InstallationRate.is_fixed,
    ]

    column_labels = {
        "category": "Категория",
        "power_range": "Мощность (BTU)",
        "base_price": "Базовая цена",
        "extra_pipe_price": "Доп. метр",
        "included_pipe_meters": "Включено метров",
        "is_fixed": "Фиксирована",
        "comment": "Комментарий",
    }

    form_columns = "__all__"
