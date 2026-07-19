# services/description_generator.py
from sqlalchemy.ext.asyncio import AsyncSession
from crud.product import ProductDAO
from models import Product, Tag
from services.product_area import area_from_specs

class DescriptionGeneratorService:
    @staticmethod
    async def generate(session: AsyncSession, product_id: int) -> str:
        # 1. Получаем данные (без изменений)
        product = await ProductDAO.get_for_generation(session, product_id)
        if not product:
            return "Ошибка: Товар не найден."

        tags_map = {}
        for tag in product.tags:
            if tag.group:
                if tag.group.slug not in tags_map:
                    tags_map[tag.group.slug] = []
                tags_map[tag.group.slug].append(tag)

        blocks = []

        # --- Блок 1: ВСТУПЛЕНИЕ (Исправили связку) ---
        area_tag = tags_map.get('area', [None])[0]
        # Если сниппет начинается с глагола (например "обладает..."), убираем "это"
        # Универсальный вариант:
        area = area_from_specs(product.specs)
        area_text = area_tag.ai_snippet if (area_tag and area_tag.ai_snippet) else f"рассчитана на помещение до {area or 0:g} кв.м"
        
        # Хитрость: Если сниппет начинается не с "идеально...", а с глагола, лучше написать просто название + текст
        intro = f"Сплит-система **{product.title}** {area_text}."
        # Если сниппет был "обладает...", получится: "Сплит-система MDV обладает..." (Идеально!)
        blocks.append(intro)

        # --- Блок 2: ЗАВОД (Тут все было хорошо) ---
        factory_tags = tags_map.get('factory-origin', [])
        for t in factory_tags:
            if t.ai_snippet:
                blocks.append(f"Главное преимущество модели: она {t.ai_snippet}.")

        # --- Блок 3: КОМФОРТ (Добавили глагол "обеспечивает") ---
        noise_tags = tags_map.get('noise-level', [])
        for t in noise_tags:
            if t.ai_snippet:
                # Было: "кондиционер комфортный фон" -> Стало: "кондиционер обеспечивает комфортный фон"
                blocks.append(f"В плане комфорта прибор обеспечивает {t.ai_snippet}.")
        
        # --- Блок 4: ТЕХНИКА ---
        tech_sentences = []
        comp_tags = tags_map.get('compressor-type', [])
        for t in comp_tags:
             if t.ai_snippet: tech_sentences.append(t.ai_snippet)
        
        brand_tags = tags_map.get('compressor-brand', [])
        for t in brand_tags:
             if t.ai_snippet: tech_sentences.append(f"сердце системы — {t.ai_snippet}")
        
        if tech_sentences:
            # Делаем первую букву заглавной
            text = ", ".join(tech_sentences)
            blocks.append(f"Техническая начинка на высоте: {text}.")

        # --- Блок 5: ФУНКЦИОНАЛ ---
        feature_tags = tags_map.get('features', [])
        features_text = []
        for t in feature_tags:
            if t.ai_snippet:
                features_text.append(t.ai_snippet)
        
        if features_text:
            blocks.append("Функциональные особенности: " + "; ".join(features_text) + ".")

        # --- Блок 6: ДИЗАЙН ---
        design_tags = tags_map.get('design', [])
        for t in design_tags:
            if t.ai_snippet:
                blocks.append(f"Внешний вид: {t.ai_snippet}.")

        # --- Блок 7: ВЕРДИКТ ---
        status_tags = tags_map.get('internal-status', [])
        is_recommended = any(t.slug in ['status-recommended', 'status-bestseller'] for t in status_tags)
        # Gree/Midea/Haier считаем топами автоматически
        is_top_factory = any(t.slug in ['factory-gree', 'factory-midea', 'factory-haier'] for t in factory_tags)

        if is_recommended or is_top_factory:
            blocks.append("\n🏆 **Вердикт команды:** Рекомендуем эту модель как одну из самых надежных в своем классе по соотношению цена/качество.")

        return " ".join(blocks)
