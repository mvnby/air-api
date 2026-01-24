import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from crud.order import OrderDAO
from models import Order, OrderProductLink, OrderServiceLink, Customer, CustomerType, OrderStatus, Product

logger = logging.getLogger(__name__)

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
    async def create_from_website(
        session: AsyncSession,
        customer_name: str,
        customer_phone: str,
        customer_email: Optional[str],
        customer_address: Optional[str],
        items: List[Dict[str, Any]]  # [{"product_id": int, "quantity": int}]
    ) -> Order:
        """
        Create order from website checkout.
        
        Handles:
        1. Customer lookup/creation by phone
        2. Order creation with NEW_LEAD status
        3. Product linking with current prices
        4. Total calculation
        
        Args:
            session: Database session
            customer_name: Customer full name
            customer_phone: Phone number (used for lookup)
            customer_email: Optional email
            customer_address: Delivery address
            items: List of cart items [{product_id, quantity}]
            
        Returns:
            Created Order with calculated totals
        """
        phone_clean = customer_phone.strip()
        
        # 1. Find or create customer
        stmt = select(Customer).where(Customer.phone == phone_clean)
        result = await session.execute(stmt)
        customer = result.scalar_one_or_none()
        
        if not customer:
            customer = Customer(
                name=customer_name,
                phone=phone_clean,
                email=customer_email,
                type=CustomerType.individual,
                actual_address=customer_address
            )
            session.add(customer)
            await session.flush()
            logger.info(f"Created new customer: {customer.name} ({customer.phone})")
        else:
            # Update address if provided
            if customer_address:
                customer.actual_address = customer_address
                session.add(customer)

        # 2. Create order
        order = Order(
            customer_id=customer.id,
            delivery_address=customer_address,
            status=OrderStatus.NEW_LEAD,
            title=f"Заказ с сайта от {datetime.now().strftime('%d.%m %H:%M')}",
            created_at=datetime.now()
        )
        session.add(order)
        await session.flush()
        
        # 3. Add items with current prices
        total_amount = 0.0
        added_items = []
        
        for item in items:
            product = await session.get(Product, item["product_id"])
            if product:
                link = OrderProductLink(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=item["quantity"],
                    price=product.price,
                    cost=0
                )
                session.add(link)
                total_amount += product.price * item["quantity"]
                added_items.append(f"{product.title} x{item['quantity']}")
            else:
                logger.warning(f"Product {item['product_id']} not found in order creation")
        
        # 4. Update totals and commit
        order.total_amount = total_amount
        session.add(order)
        await session.commit()
        await session.refresh(order)
        
        # Log
        logger.info(
            f"NEW ORDER #{order.id} | Customer: {customer.name} ({customer.phone}) | "
            f"Total: {total_amount} RUB | Items: {len(added_items)}"
        )
        logger.debug(f"Order #{order.id} items: {', '.join(added_items)}")
        
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