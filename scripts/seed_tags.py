import asyncio
from sqlmodel import select
from database import async_session_maker, engine, init_db
from models import TagGroup, Tag
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA = {
  "data": [
    {
      "title": "Площадь / Мощность",
      "slug": "area",
      "sort_order": 10,
      "is_public": True,
      "allow_multiple": False,
      "tags": [
        { "title": "До 20 м² (07)", "slug": "area-20", "sort_order": 10, "ai_snippet": "идеально подходит для небольших комнат и спален площадью до 20 кв.м", "is_filter": True },
        { "title": "До 25 м² (09)", "slug": "area-25", "sort_order": 20, "ai_snippet": "оптимальное решение для стандартных комнат до 25 кв.м", "is_filter": True },
        { "title": "До 35 м² (12)", "slug": "area-35", "sort_order": 30, "ai_snippet": "обладает достаточной мощностью для охлаждения гостиной до 35 кв.м", "is_filter": True },
        { "title": "До 50 м² (18)", "slug": "area-50", "sort_order": 40, "ai_snippet": "мощная система для просторных помещений и студий до 50 кв.м", "is_filter": True },
        { "title": "50 м² и более (24+)", "slug": "area-50-plus", "sort_order": 50, "ai_snippet": "высокопроизводительная модель для офисов и больших залов", "is_filter": True }
      ]
    },
    {
      "title": "Тип компрессора",
      "slug": "compressor-type",
      "sort_order": 20,
      "is_public": True,
      "allow_multiple": False,
      "tags": [
        { "title": "On/Off (Классический)", "slug": "on-off", "sort_order": 20, "reliability_score": 0.8, "ai_snippet": "надежная классическая система типа On/Off", "is_filter": True },
        { "title": "Инвертор (Inverter)", "slug": "inverter", "sort_order": 10, "reliability_score": 1.0, "ai_snippet": "современный инверторный компрессор обеспечивает экономию энергии и точное поддержание температуры", "is_filter": True },
        { "title": "Full DC Inverter", "slug": "full-dc", "sort_order": 5, "reliability_score": 1.1, "ai_snippet": "премиальный Full DC инвертор с максимальной энергоэффективностью и тишиной", "is_filter": True }
      ]
    },
    {
      "title": "Завод-изготовитель (Реальный)",
      "slug": "factory-origin",
      "sort_order": 30,
      "is_public": True,
      "allow_multiple": False,
      "tags": [
        { "title": "Сборка Gree", "slug": "factory-gree", "sort_order": 10, "reliability_score": 1.0, "ai_snippet": "модель собрана на заводе Gree — мирового лидера климатической техники", "is_filter": True },
        { "title": "Сборка Midea", "slug": "factory-midea", "sort_order": 20, "reliability_score": 1.0, "ai_snippet": "производится на технологичных линиях завода Midea, известного своей надежностью", "is_filter": True },
        { "title": "Сборка Haier", "slug": "factory-haier", "sort_order": 30, "reliability_score": 0.95, "ai_snippet": "качественная заводская сборка Haier", "is_filter": True },
        { "title": "Сборка AUX", "slug": "factory-aux", "sort_order": 40, "reliability_score": 0.9, "ai_snippet": "изготовлена на заводе AUX (оптимальный средний сегмент)", "is_filter": True },
        { "title": "Сборка TCL", "slug": "factory-tcl", "sort_order": 50, "reliability_score": 0.8, "ai_snippet": "бюджетное решение, собранное на мощностях TCL", "is_filter": True },
        { "title": "OEM (Неизвестный/Бюджет)", "slug": "factory-unknown", "sort_order": 99, "reliability_score": 0.6, "ai_snippet": "доступная модель базового уровня", "is_filter": False }
      ]
    },
    {
      "title": "Уровень шума (Экспертная оценка)",
      "slug": "noise-level",
      "sort_order": 40,
      "is_public": True,
      "allow_multiple": False,
      "tags": [
        { "title": "Silent (Спальня)", "slug": "noise-silent", "sort_order": 10, "ai_snippet": "отличается практически бесшумной работой, идеально подходит для спален", "is_filter": True },
        { "title": "Comfort (Гостиная)", "slug": "noise-comfort", "sort_order": 20, "ai_snippet": "комфортный акустический фон, слышен только легкий поток воздуха", "is_filter": True },
        { "title": "Standard (Офис/Кухня)", "slug": "noise-standard", "sort_order": 30, "ai_snippet": "стандартный уровень шума, подходит для жилых комнат днем или коммерческих помещений", "is_filter": True }
      ]
    },
    {
      "title": "Функционал",
      "slug": "features",
      "sort_order": 50,
      "is_public": True,
      "allow_multiple": True,
      "tags": [
        { "title": "Wi-Fi встроенный", "slug": "wifi-builtin", "sort_order": 10, "ai_snippet": "имеет встроенный модуль Wi-Fi для управления климатом со смартфона", "is_filter": True },
        { "title": "Wi-Fi опция (Ready)", "slug": "wifi-ready", "sort_order": 20, "ai_snippet": "поддерживает установку Wi-Fi модуля (приобретается отдельно)", "is_filter": True },
        { "title": "УФ-лампа / Ионизация", "slug": "health-air", "sort_order": 30, "ai_snippet": "оснащен системой активной очистки и обеззараживания воздуха", "is_filter": True },
        { "title": "Приток свежего воздуха", "slug": "fresh-air", "sort_order": 40, "ai_snippet": "уникальная функция подмеса свежего воздуха с улицы", "is_filter": True },
        { "title": "Работа до -25°C (Обогрев)", "slug": "winter-heat", "sort_order": 50, "ai_snippet": "адаптирован для эффективной работы на обогрев даже в сильные морозы (до -25°C)", "is_filter": True }
      ]
    },
    {
      "title": "Дизайн",
      "slug": "design",
      "sort_order": 60,
      "is_public": True,
      "allow_multiple": False,
      "tags": [
        { "title": "Матовый корпус", "slug": "design-matte", "sort_order": 10, "ai_snippet": "стильный матовый корпус выглядит дорого и не создает бликов", "is_filter": True },
        { "title": "Черный / Дизайнерский", "slug": "design-color", "sort_order": 20, "ai_snippet": "эффектный темный корпус станет ярким акцентом в современном интерьере", "is_filter": True },
        { "title": "Компактный (Slim)", "slug": "design-slim", "sort_order": 30, "ai_snippet": "компактный внутренний блок, сохраняющий пространство", "is_filter": True }
      ]
    },
    {
      "title": "Внутренний статус (Служебное)",
      "slug": "internal-status",
      "sort_order": 99,
      "is_public": False,
      "allow_multiple": True,
      "tags": [
        { "title": "Выбор сервиса (Рекомендуем)", "slug": "status-recommended", "sort_order": 1, "reliability_score": 1.2, "ai_snippet": "мы рекомендуем эту модель как одну из самых надежных", "is_public": True, "is_filter": True },
        { "title": "Хит продаж", "slug": "status-bestseller", "sort_order": 2, "reliability_score": 1.1, "ai_snippet": "абсолютный хит продаж благодаря балансу цены и качества", "is_public": True, "is_filter": True },
        { "title": "Надежный поставщик", "slug": "supplier-good", "sort_order": 10, "reliability_score": 1.0, "is_public": False, "is_filter": False },
        { "title": "Проблемный поставщик", "slug": "supplier-bad", "sort_order": 20, "reliability_score": 0.5, "is_public": False, "is_filter": False },
        { "title": "Высокая маржа", "slug": "margin-high", "sort_order": 30, "reliability_score": 1.1, "is_public": False, "is_filter": False }
      ]
    }
  ]
}

async def seed():
    await init_db()
    logger.info("Starting seed...")
    async with async_session_maker() as session:
        for group_data in DATA["data"]:
            # Find or Create Group
            stmt = select(TagGroup).where(TagGroup.slug == group_data["slug"])
            result = await session.execute(stmt)
            group = result.scalar_one_or_none()
            
            if not group:
                logger.info(f"Creating Group: {group_data['title']}")
                group = TagGroup(
                    title=group_data["title"],
                    slug=group_data["slug"],
                    sort_order=group_data["sort_order"],
                    is_public=group_data["is_public"],
                    allow_multiple=group_data["allow_multiple"]
                )
                session.add(group)
                await session.commit()
                await session.refresh(group)
            else:
                logger.info(f"Updating Group: {group_data['title']}")
                group.title = group_data["title"]
                group.sort_order = group_data["sort_order"]
                group.is_public = group_data["is_public"]
                group.allow_multiple = group_data["allow_multiple"]
                session.add(group)
                await session.commit()
            
            # Process Tags
            for tag_data in group_data["tags"]:
                stmt = select(Tag).where(Tag.slug == tag_data["slug"])
                result = await session.execute(stmt)
                tag = result.scalar_one_or_none()
                
                if not tag:
                    logger.info(f"  Creating Tag: {tag_data['title']}")
                    tag = Tag(
                        group_id=group.id,
                        title=tag_data["title"],
                        slug=tag_data["slug"],
                        sort_order=tag_data.get("sort_order", 0),
                        is_public=tag_data.get("is_public", True),
                        is_filter=tag_data.get("is_filter", False),
                        ai_snippet=tag_data.get("ai_snippet"),
                        reliability_score=tag_data.get("reliability_score")
                    )
                    session.add(tag)
                else:
                    logger.info(f"  Updating Tag: {tag_data['title']}")
                    tag.group_id = group.id
                    tag.title = tag_data["title"]
                    # slug is immutable-ish for identity here, but updated if needed
                    tag.sort_order = tag_data.get("sort_order", 0)
                    tag.is_public = tag_data.get("is_public", True)
                    tag.is_filter = tag_data.get("is_filter", False)
                    tag.ai_snippet = tag_data.get("ai_snippet")
                    tag.reliability_score = tag_data.get("reliability_score")
                    session.add(tag)
            
            await session.commit()
            
    logger.info("Seed completed.")

if __name__ == "__main__":
    asyncio.run(seed())
