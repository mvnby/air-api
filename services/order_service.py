from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.order import OrderDAO
from models import Order, OrderProductLink, OrderServiceLink

class OrderService:
    @staticmethod
    async def create_order(
        session: AsyncSession,
        user_id: int,
        contact_info: str, # Телефон или адрес
        items_data: Dict[str, Any], # Словарь с товарами
        username: Optional[str] = None,
        full_name: Optional[str] = None
    ) -> Order:
        """
        Create order and populate it with items.
        """
        # 1. Создаем сам заказ
        order = await OrderDAO.create(
            session,
            user_id=user_id,
            phone=contact_info,
            username=username,
            full_name=full_name
        )
        
        # 2. Наполняем товарами
        if items_data:
            await OrderService.update_order_links(session, order.id, items_data)
        
        return order

    @staticmethod
    async def update_order_links(session: AsyncSession, order_id: int, items_data: Dict[str, Any]) -> None:
        """
        Full sync of order items (products/services).
        Uses current DB prices for products.
        """
        # 1. Очищаем старые связи
        await OrderDAO.clear_product_links(session, order_id)
        await OrderDAO.clear_service_links(session, order_id)
        
        # 2. Добавляем товары
        for p in items_data.get("products", []):
            link = OrderProductLink(
                order_id=order_id,
                product_id=p["product_id"],
                quantity=p["quantity"],
                price=p["price"] # Цена должна приходить актуальная
            )
            session.add(link)
        
        # 3. Добавляем услуги
        for s in items_data.get("services", []):
            link = OrderServiceLink(
                order_id=order_id,
                service_id=s["service_id"],
                quantity=s["quantity"],
                price=s["price"]
            )
            session.add(link)
            
        # session.add_all(new_links) - Removed as items are added in loop
        await session.flush() # Ensure links are in DB

        # 4. Пересчитываем итоговые цифры заказа
        # Необходимо подгрузить связи, чтобы calculate_totals отработал корректно
        # Используем существующий метод DAO или подгружаем вручную
        order = await OrderDAO.get_with_links(session, order_id)
        if order:
            order.calculate_totals()
            session.add(order)
            
        await session.commit()

    @staticmethod
    async def update_order_installers(session: AsyncSession, order_id: int, installers_data: List[Dict[str, Any]]) -> None:
        """
        Updates installers for an order and triggers notifications for NEW assignments.
        """
        from models import OrderInstaller, Installer
        from services.bot_service import BotService
        
        # 1. Забираем текущие назначения чтобы понять, кто новый
        existing = await session.execute(select(OrderInstaller).where(OrderInstaller.order_id == order_id))
        existing_map = {i.installer_id: i for i in existing.scalars().all()}
        
        # 2. Очищаем старые (или обновляем, но для простоты пересоздадим)
        # В идеале нужно делать diff, но пока просто удалим те, кого нет в новом списке
        # Хотя для уведомлений нужно знать именно добавленных.
        
        new_installer_ids = {int(i['installer_id']) for i in installers_data}
        
        # Удаляем тех, кого нет в новом списке
        for i_id, link in list(existing_map.items()):
            if i_id not in new_installer_ids:
                await session.delete(link)
        
        # 3. Добавляем/Обновляем
        added_installers = []
        for i_data in installers_data:
            i_id = int(i_data['installer_id'])
            if i_id not in existing_map:
                # Это новый!
                item = OrderInstaller(
                    order_id=order_id,
                    installer_id=i_id,
                    role=i_data.get('role', 'main'),
                    agreed_pay=float(i_data.get('agreed_pay', 0))
                )
                session.add(item)
                added_installers.append(i_id)
            else:
                # Обновляем существующего
                existing_item = existing_map[i_id]
                existing_item.agreed_pay = float(i_data.get('agreed_pay', 0))
                existing_item.role = i_data.get('role', 'main')
                session.add(existing_item)
        
        await session.flush()
        
        # 4. Триггер уведомлений для НОВЫХ
        if added_installers:
            # Подгружаем детали для сообщения
            order = await OrderDAO.get_with_links(session, order_id)
            # Подгружаем самих монтажников чтобы узнать telegram_id
            res = await session.execute(select(Installer).where(Installer.id.in_(added_installers)))
            installers_to_notify = res.scalars().all()
            
            for inst in installers_to_notify:
                if inst.telegram_id:
                    await BotService.notify_installer_new_order(
                        installer_tg_id=inst.telegram_id,
                        order_id=order_id,
                        address=order.delivery_address or "Адрес не указан",
                        date_str=order.installation_date.strftime("%d.%m.%Y") if order.installation_date else "Не назначена",
                        role="Монтажник" # Можно уточнить из связи
                    )

        # Пересчет
        order = await OrderDAO.get_with_links(session, order_id)
        if order:
            order.calculate_totals()
            session.add(order)
            
        await session.commit()
    
    # ... остальные методы (get_all_orders, update_status) остаются без изменений ...
    @staticmethod
    async def get_all_orders(session: AsyncSession) -> List[Order]:
        return await OrderDAO.get_all(session)

    @staticmethod
    async def update_status(session: AsyncSession, order_id: int, new_status: Any) -> bool:
        """Update order status."""
        return await OrderDAO.update_status(session, order_id, new_status)