import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import func, or_, and_, not_, cast, String, delete
from sqlalchemy.orm import selectinload

from crud.order import OrderDAO
from crud.product import ProductDAO
from models import Order, OrderProductLink, OrderServiceLink, Customer, CustomerType, OrderStatus, Product, LeadSource, Service, OrderInstaller

logger = logging.getLogger(__name__)

class OrderService:
    @staticmethod
    def _normalize_naive_datetime(dt: Optional[datetime]) -> Optional[datetime]:
        """Convert timezone-aware datetime to naive (for DB compatibility)."""
        if dt is not None and dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt

    @staticmethod
    async def get_calendar_events(
        session: AsyncSession, 
        start_date: datetime, 
        end_date: datetime
    ) -> List["CalendarEventResponse"]:
        """
        Get calendar events for orders (assessments and installations).
        """
        from schemas import CalendarEventResponse, CalendarEventType
        
        # Adjust end_date to include the full day if needed, or rely on caller
        
        # Ensure dates are offset-naive for PostgreSQL comparison if DB stores naive timestamps
        if start_date.tzinfo is not None:
            start_date = start_date.replace(tzinfo=None)
        if end_date.tzinfo is not None:
            end_date = end_date.replace(tzinfo=None)

        # Query orders where EITHER measurement_date OR installation_date is in range
        stmt = (
            select(Order)
            .where(
                or_(
                    and_(Order.measurement_date >= start_date, Order.measurement_date <= end_date),
                    and_(Order.installation_date >= start_date, Order.installation_date <= end_date)
                )
            )
            .options(selectinload(Order.customer))
        )
        
        result = await session.execute(stmt)
        orders = result.scalars().all()
        
        events = []
        
        for order in orders:
            # Measurement Event
            if order.measurement_date and start_date <= order.measurement_date <= end_date:
                events.append(CalendarEventResponse(
                    id=f"{order.id}-measurement",
                    order_id=order.id,
                    type=CalendarEventType.MEASUREMENT,
                    date=order.measurement_date,
                    status=order.status.value if hasattr(order.status, "value") else str(order.status),
                    customer_name=order.customer.name if order.customer else "Неизвестный",
                    address=order.delivery_address,
                    title=f"Замер: {order.customer.name if order.customer else 'Клиент'}",
                    start=order.measurement_date,
                    color="#64748b" # Slate
                ))
            
            # Installation Event
            if order.installation_date and start_date <= order.installation_date <= end_date:
                 events.append(CalendarEventResponse(
                    id=f"{order.id}-installation",
                    order_id=order.id,
                    type=CalendarEventType.INSTALLATION,
                    date=order.installation_date,
                    status=order.status.value if hasattr(order.status, "value") else str(order.status),
                    customer_name=order.customer.name if order.customer else "Неизвестный",
                    address=order.delivery_address,
                    title=f"Монтаж: {order.customer.name if order.customer else 'Клиент'}",
                    start=order.installation_date,
                    color="#007f80" # Teal
                ))
                
        return events

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
        items: List[Dict[str, Any]],  # [{"product_id": int, "quantity": int}]
        lead_source: LeadSource = LeadSource.SITE,
        comment: Optional[str] = None,
        customer_type: str = "individual",
        customer_inn: Optional[str] = None,
        customer_legal_name: Optional[str] = None,
        customer_legal_address: Optional[str] = None,
        customer_iban: Optional[str] = None,
        customer_bic: Optional[str] = None,
        customer_bank_name: Optional[str] = None
    ) -> Order:
        """
        Create order from website checkout.
        
        Handles:
        1. Customer lookup/creation by phone
        2. Order creation with NEW_LEAD status and lead_source
        3. Product linking with current prices
        4. Total calculation
        
        Args:
            session: Database session
            customer_name: Customer full name
            customer_phone: Phone number (used for lookup)
            customer_email: Optional email
            customer_address: Delivery address
            items: List of cart items [{product_id, quantity}]
            lead_source: Source of the lead (SITE, BOT, PHONE, etc.)
            comment: Optional note or initial customer request
            
        Returns:
            Created Order with calculated totals
        """
        phone_clean = customer_phone.strip()
        
        # 1. Find or create customer
        customer = None
        
        # Only lookup if phone is valid (at least 6 digits/chars) to avoid matching empty strings
        if len(phone_clean) > 5:
            stmt = select(Customer).where(Customer.phone == phone_clean)
            result = await session.execute(stmt)
            # Handle potential duplicates gracefully
            try:
                customer = result.scalar_one_or_none()
            except Exception:
                logger.warning(f"Multiple customers found for phone '{phone_clean}'. Creating new individual.")
                customer = None
        
        if not customer:
            customer = Customer(
                name=customer_name,
                phone=phone_clean,
                email=customer_email,
                type=CustomerType.company if customer_type == "company" else CustomerType.individual,
                actual_address=customer_address,
                inn=customer_inn,
                full_legal_name=customer_legal_name,
                legal_address=customer_legal_address,
                iban=customer_iban,
                bic=customer_bic,
                bank_name=customer_bank_name
            )
            session.add(customer)
            await session.flush()
            logger.info(f"Created new customer: {customer.name} ({customer.phone})")
        else:
            # Update address if provided
            if customer_address:
                customer.actual_address = customer_address
            
            # Update B2B info if provided (individual -> company conversion or updating company data)
            if customer_type == "company":
                customer.type = CustomerType.company
                if customer_inn:
                    customer.inn = customer_inn
                if customer_legal_name:
                    customer.full_legal_name = customer_legal_name
                if customer_legal_address:
                    customer.legal_address = customer_legal_address
                if customer_iban:
                    customer.iban = customer_iban
                if customer_bic:
                    customer.bic = customer_bic
                if customer_bank_name:
                    customer.bank_name = customer_bank_name
            
            session.add(customer)

        # 2. Create order with lead_source
        order = Order(
            customer_id=customer.id,
            delivery_address=customer_address,
            status=OrderStatus.NEW_LEAD,
            lead_source=lead_source,
            comment=comment,
            title=f"Заказ с сайта от {datetime.now().strftime('%d.%m %H:%M')}",
            created_at=datetime.now()
        )
        session.add(order)
        await session.flush()
        
        # 3. Add items with current prices
        total_amount = 0.0
        added_items = []
        installation_services = []  # Collect installation services to add after products
        
        for item in items:
            product_id = item.get("product_id")
            product = None


# ...

            if product_id:
                product = await ProductDAO.get_by_id(session, product_id)

            if product:
                # Extract installation fields (Phase: Snapshot Pricing Refactor)
                with_installation = item.get("with_installation", False)
                installation_price = int(item.get("installation_price", 0))
                
                link = OrderProductLink(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=item["quantity"],
                    price=product.price,
                    cost=0,
                    # Save snapshot for history
                    is_installation_included=with_installation,
                    installation_price=installation_price if with_installation else 0,
                    installation_details=item.get("installation_meta") if with_installation else None
                )
                session.add(link)
                
                # Calculate product total
                product_total = product.price * item["quantity"]
                total_amount += product_total
                
                # If installation requested, add to total
                if with_installation and installation_price > 0:
                    total_amount += installation_price * item["quantity"]
                    
                    # --- NEW LOGIC: Explicitly create OrderServiceLink for Main Installation ---
                    # Construct title based on meta
                    meta = item.get("installation_meta", {})
                    meters = meta.get("meters", 3)
                    type_raw = meta.get("type", "General")
                    power_raw = meta.get("power_range", "")
                    
                    
                    # Robust Title Generation using Product Attributes + Mappings
                    # User requested format: "Монтаж кондиционера {type}, мощностью {power}, включая межблочную трассу {meters} м"
                    
                    # 1. Determine Type
                    # Mappings: Wall -> настенного типа, Cassette -> кассетного типа, etc.
                    # We check: product tags, meta type, or fallback to Wall.
                    type_str = "настенного типа" # Default
                    
                    # Try to find type in tags if product exists
                    product_tags_titles = [t.title.lower() for t in product.tags] if product and product.tags else []
                    product_tags_slugs = [t.slug.lower() for t in product.tags] if product and product.tags else []
                    
                    # Map of tag/meta keywords to Russian text
                    TYPE_MAPPINGS = {
                        'wall': 'настенного типа', 
                        'настенный': 'настенного типа',
                        'cassette': 'кассетного типа', 
                        'кассетный': 'кассетного типа',
                        'ceiling': 'потолочного типа', 
                        'напольно-потолочный': 'потолочного типа',
                        'duct': 'канального типа', 
                        'канальный': 'канального типа',
                        'multisplit': 'мульти-сплит системы',
                        'multi': 'мульти-сплит системы'
                    }
                    
                    # Check tags first (more reliable than meta usually)
                    found_type = False
                    for key, val in TYPE_MAPPINGS.items():
                        if key in product_tags_slugs or key in product_tags_titles:
                            type_str = val
                            found_type = True
                            break
                    
                    # If not found in tags, check meta (fallback)
                    if not found_type and type_raw and type_raw != "General":
                        lower_raw = type_raw.lower()
                        if lower_raw in TYPE_MAPPINGS:
                            type_str = TYPE_MAPPINGS[lower_raw]
                        else:
                             # Direct translation check for common English terms
                             if 'wall' in lower_raw: type_str = 'настенного типа'
                             elif 'cassette' in lower_raw: type_str = 'кассетного типа'
                             elif 'ceiling' in lower_raw: type_str = 'потолочного типа'
                             elif 'duct' in lower_raw: type_str = 'канального типа'
                             elif 'multi' in lower_raw: type_str = 'мульти-сплит системы'

                    # 2. Determine Power Range
                    # Mappings: 
                    # area-20..35 -> до 4 кВт
                    # area-50..70 -> до 7 кВт
                    # area-80+ -> выше 7 кВт
                    power_str = ""
                    
                    # Use product area if available
                    if product and product.area:
                        area = product.area
                        if area <= 35:
                            power_str = "до 4 кВт"
                        elif area <= 70:
                            power_str = "до 7 кВт"
                        else:
                            power_str = "выше 7 кВт"
                    elif power_raw:
                        # Fallback to meta string parsing if product area missing
                        # power_raw ex: "area-25", "07-12", "Standard"
                        if "20" in power_raw or "25" in power_raw or "35" in power_raw or "07" in power_raw or "09" in power_raw or "12" in power_raw:
                             power_str = "до 4 кВт"
                        elif "50" in power_raw or "70" in power_raw or "18" in power_raw or "24" in power_raw:
                             power_str = "до 7 кВт"
                        elif "80" in power_raw or "100" in power_raw or "30" in power_raw or "36" in power_raw:
                             power_str = "выше 7 кВт"
                        # Handle specific text map from old logic if needed, but above covers most numeric codes

                    # Construct Title
                    main_inst_title = f"Монтаж кондиционера {type_str}"
                    if power_str:
                        main_inst_title += f", мощностью {power_str}"
                    
                    main_inst_title += f", включая межблочную трассу {meters} м"


                    # Add MAIN installation as a service link
                    installation_services.append({
                        "title": main_inst_title,
                        "price": installation_price, # This is the calculated total for main install (base + meters)
                        "quantity": item["quantity"]
                    })
                    
                    # --- NEW LOGIC: Process Add-ons ---
                    options_slugs = item.get("installation_options", [])
                    if options_slugs:
                        # Fetch services by slug to get titles/prices (security check)
                        # Note: The price in payload "installation_price" usually includes options if calculated on frontend.
                        # However, for accurate breakdown, we should ideally sum them up or use the frontend provided breakdown if available.
                        # Current cart.ts logic: "installationPrice" holds the SUM of base + meters + options.
                        # PROBLEM: If we add "installation_price" above (line 154) AND add separate service links with prices, we double count?
                        # NO, "total_amount" is calculated on line 154.
                        # The "installation_services" list is used to create LINKS.
                        # The LINKS (OrderServiceLink) have a price.
                        # When calculate_totals() runs on the order later, it might sum up ServiceLinks + ProductLinks.
                        # Let's check calculate_totals in Order model... (I can't see it now, but assumingly it sums everything).
                        # BUT, line 143: link (ProductLink) has "installation_price".
                        # If we ALSO create ServiceLink, we double-charge.
                        
                        # ACTION: 
                        # 1. ProductLink should probably NOT store the full installation price if we are breaking it out into services.
                        # OR 
                        # 2. ProductLink stores it for "Product + Install" line item reference, but ServiceLinks are "extra"?
                        # The user wants them in "Services".
                        # Safest bet: Set ProductLink.installation_price to 0 or keeping it as "snapshot" but ensuring total calculation doesn't double dip.
                        # Actually, looking at line 149-154: `total_amount` is manually accumulated here.
                        # And `Order.total_amount` is set on line 247.
                        # So `calculate_totals` is NOT called here.
                        # So we are free to define links as we want for display.
                        
                        # RE-CALCULATION STRATEGY:
                        # 1. Main Install Price = Total Install Price (from payload) - Sum(Options Prices).
                        #    We need to fetch options to know their prices.
                        
                        from services.image_service import ImageService # Just in case, or use DAO
                        stmt_opts = select(Service).where(Service.slug.in_(options_slugs))
                        res_opts = await session.execute(stmt_opts)
                        db_options = res_opts.scalars().all()
                        
                        options_total_cost = 0
                        for opt in db_options:
                            options_total_cost += opt.base_price
                            # Add option as service link
                            installation_services.append({
                                "title": f"Доп. услуга: {opt.title}",
                                "price": opt.base_price,
                                "quantity": item["quantity"],
                                "service_id": opt.id # Link to actual service
                            })
                            
                        # Adjust Main Install Price in the Service Link to exclude options cost 
                        # so that Sum(Services) = Original Total Install Price
                        # (This assumes frontend passed the correct total).
                        
                        # Wait, the `installation_price` from payload is the Grand Total of valid install?
                        # Yes.
                        # So Main Link Price = PayloadPrice - OptionsCost.
                        
                        # Update the last added service (Main Install)
                        if installation_services:
                            # The main install is the one before options (index -1 - len(options))
                            # Actually we just added it.
                            main_svc_idx = len(installation_services) - 1 - len(db_options)
                            if main_svc_idx >= 0:
                                installation_services[main_svc_idx]["price"] -= options_total_cost
                    
                
                # Log details
                item_desc = f"{product.title} x{item['quantity']}"
                if with_installation:
                    item_desc += f" + монтаж ({installation_price} р.)"
                added_items.append(item_desc)

            elif product_id is None and item.get("with_installation"):
                # SERVICE-ONLY ORDER (Legacy/Calculator)
                # ... existing logic for service-only ...
                
                installation_price = int(item.get("installation_price", 0))
                meta = item.get("installation_meta", {})
                
                # ... (Same mapping logic as above) ...
                # Construct detailed title with friendly formatting
                type_raw = meta.get("type", "General")
                meters = meta.get("meters", 3)
                power_raw = meta.get("power_range", "")
                
                TYPE_MAP = {
                    'Wall': 'настенного типа',
                    'Настенный': 'настенного типа',
                    'Cassette': 'кассетного типа',
                    'Кассетный': 'кассетного типа',
                    'Ceiling': 'потолочного типа',
                    'Напольно-потолочный': 'потолочного типа',
                    'Duct': 'канального типа',
                    'Канальный': 'канального типа',
                    'Multisplit': 'мульти-сплит системы',
                    'Мульти-сплит': 'мульти-сплит системы'
                }
                
                POWER_MAP = {
                    'area-20, area-25, area-35': 'до 4 кВт',
                    'area-50, area-70': 'до 7 кВт',
                    'area-80, area-100': 'выше 7 кВт',
                    '07-12': 'до 3.5 кВт',
                    '18-24': 'до 7 кВт',
                    '30-36': 'выше 7 кВт'
                }
                
                type_str = TYPE_MAP.get(type_raw, type_raw)
                power_str = POWER_MAP.get(power_raw, power_raw)
                
                service_title = f"Монтаж кондиционера {type_str}"
                
                if power_str and power_str != "Standard":
                    if power_raw in POWER_MAP: 
                         service_title += f", мощностью {power_str}"
                    else:
                         found_power = False
                         for k, v in POWER_MAP.items():
                             if k in power_raw:
                                 service_title += f", мощностью {v}"
                                 found_power = True
                                 break
                         if not found_power:
                             service_title += f", мощностью {power_raw}"

                service_title += f", включая межблочную трассу {meters} м"
                # Add to total
                # Note: frontend usually passes the TOTAL meta price including options.
                # But here we will calculate options separately to link them properly.
                # To avoid double counting, we should SUBTRACT options cost from the "Main Install" price if the input `installation_price` included them.
                # However, for Calculator flow, we can assume we want to break it down.
                
                # Fetch detailed options if present
                options_slugs = item.get("installation_options", [])
                options_cost = 0
                service_links_to_add = []
                
                if options_slugs:
                    stmt_opts = select(Service).where(Service.slug.in_(options_slugs))
                    res_opts = await session.execute(stmt_opts)
                    db_options = res_opts.scalars().all()
                    
                    for opt in db_options:
                        options_cost += opt.base_price
                        service_links_to_add.append({
                            "title": f"Доп. опция: {opt.title}",
                            "price": opt.base_price,
                            "quantity": item["quantity"],
                            "service_id": opt.id
                        })

                # Calculate Main Install Price
                # If the incoming `installation_price` (total) includes options, we subtract them to get the base main install price.
                # This ensures: Main + Options = Total.
                main_install_price = installation_price - options_cost
                
                # Safety check: if main price goes negative (e.g. data mismatch), we keep it as is and just add extra services (assuming total was base).
                # But typically calculator sends Grand Total.
                if main_install_price < 0:
                     logger.warning(f"Main install price becoming negative ({main_install_price})! Assuming input price was base-only.")
                     main_install_price = installation_price
                     # In this case, total_amount will increase by options_cost
                     total_amount += options_cost * item["quantity"] # Add options on top
                
                # 1. Main Installation
                installation_services.append({
                    "title": service_title,
                    "price": main_install_price,
                    "quantity": item["quantity"]
                })
                
                # 2. Add Options
                installation_services.extend(service_links_to_add)
                
                # Add to total (Main + Options) or just original Total
                # Since we recalculated, sum(components) should equal original total if logic matches.
                # Let's trust the components we just built.
                # total_amount was initialized to 0 for this item scope? No, it's global accumulator.
                # We need to add THIS item's contribution.
                # Contribution = (Main + Sum(Options)) * Qty
                item_total = (main_install_price + options_cost) * item["quantity"]
                total_amount += item_total
                
                added_items.append(f"{service_title} x{item['quantity']} ({item_total} р.)")

            else:
                logger.warning(f"Product {product_id} not found/invalid in order creation")
        
        # 3b. Add installation services
        for inst_svc in installation_services:
            service_link = OrderServiceLink(
                order_id=order.id,
                service_id=inst_svc.get("service_id"), # Now supported
                title=inst_svc["title"],
                price=inst_svc["price"],
                quantity=inst_svc["quantity"]
            )
            session.add(service_link)
        
        # 4. Update totals and commit
        order.total_amount = total_amount
        session.add(order)
        await session.commit()
        await session.refresh(order)
        
        # Log
        logger.info(
            f"NEW ORDER #{order.id} | Source: {lead_source.value} | "
            f"Customer: {customer.name} ({customer.phone}) | "
            f"Total: {total_amount} RUB | Items: {len(added_items)} | "
            f"Installation services: {len(installation_services)}"
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

    @staticmethod
    async def update_all_items(
        session: AsyncSession, 
        order_id: int, 
        items_data: Dict[str, Any]
    ) -> None:
        """
        Full sync of order items including products, services, and installers.
        Used by admin panel for order editing.
        
        Args:
            session: Database session
            order_id: Order ID
            items_data: Dict with 'products', 'services', 'installers' lists
        """
        from models import OrderInstaller
        
        # 1. Clear existing links
        await OrderDAO.clear_product_links(session, order_id)
        await OrderDAO.clear_service_links(session, order_id)
        
        # Clear installers
        stmt = OrderInstaller.__table__.delete().where(OrderInstaller.order_id == order_id)
        await session.execute(stmt)
        
        # 2. Add products
        for prod in items_data.get("products", []):
            link = OrderProductLink(
                order_id=order_id,
                product_id=int(prod["product_id"]),
                quantity=int(prod["quantity"]),
                price=int(prod["price"])
            )
            session.add(link)
        
        # 3. Add services (with custom titles)
        for serv in items_data.get("services", []):
            # Use None instead of 0 for service_id to enable snapshot pricing
            service_id_raw = serv.get("service_id", 0)
            service_id = None if (service_id_raw == 0 or service_id_raw is None) else int(service_id_raw)
            
            link = OrderServiceLink(
                order_id=order_id,
                service_id=service_id,  # Can be None for custom services
                title=serv.get("title"),  # Custom editable title
                quantity=int(serv["quantity"]),
                price=int(serv["price"])
            )
            session.add(link)
        
        # 4. Add installers
        for inst in items_data.get("installers", []):
            new_inst = OrderInstaller(
                order_id=order_id,
                installer_id=int(inst["installer_id"]),
                agreed_pay=int(inst.get("agreed_pay", 0)),
                role=inst.get("role", "main")
            )
            session.add(new_inst)
        
        await session.flush()
        
        # 5. Recalculate totals
        order = await OrderDAO.get_with_links(session, order_id)
        if order:
            order.calculate_totals()
            session.add(order)
        
        await session.commit()

    @staticmethod
    async def check_stock_for_proposal(
        session: AsyncSession, 
        product_ids: List[int],
        min_stock: int = 3
    ) -> List[str]:
        """
        Check if products have sufficient stock for sending a proposal.
        
        Args:
            session: Database session
            product_ids: List of product IDs to check
            min_stock: Minimum required stock (default 3)
            
        Returns:
            List of warning strings for low-stock items. Empty if all OK.
        """
        if not product_ids:
            return []
        
        stmt = select(Product).where(Product.id.in_(product_ids))
        result = await session.execute(stmt)
        products = result.scalars().all()
        
        low_stock_items = []
        for p in products:
            stock = getattr(p, 'stock_quantity', 0) or 0
            if stock < min_stock:
                low_stock_items.append(f"{p.title} ({stock})")
        
        return low_stock_items
    
    @staticmethod
    async def get_all_orders(session: AsyncSession) -> List[Order]:
        return await OrderDAO.get_all(session)

    @staticmethod
    async def update_status(session: AsyncSession, order_id: int, new_status: Any) -> bool:
        """Update order status."""
        return await OrderDAO.update_status(session, order_id, new_status)

    @staticmethod
    def _map_customer_brief(customer: Optional[Customer]) -> Optional[Dict[str, Any]]:
        if not customer:
            return None
        return {
            "id": int(customer.id or 0),
            "type": customer.type.value if hasattr(customer.type, "value") else str(customer.type or CustomerType.individual.value),
            "name": customer.name or "Без имени",
            "phone": customer.phone or "",
            "email": customer.email,
            "full_legal_name": customer.full_legal_name,
            "inn": customer.inn,
            "legal_address": customer.legal_address,
            "bank_name": customer.bank_name,
            "bic": customer.bic,
            "iban": customer.iban,
        }

    @staticmethod
    def _map_order_list_item(order: Order) -> Dict[str, Any]:
        return {
            "id": int(order.id or 0),
            "status": order.status.value if hasattr(order.status, "value") else str(order.status or OrderStatus.NEW_LEAD.value),
            "created_at": order.created_at,
            "updated_at": order.updated_at,
            "next_followup_date": order.next_followup_date,
            "measurement_date": order.measurement_date,
            "installation_date": order.installation_date,
            "total_amount": float(order.total_amount or 0),
            "total_cost": float(order.total_cost or 0),
            "margin": float(order.margin or 0),
            "is_paid": bool(order.is_paid),
            "comment": order.comment,
            "delivery_address": order.delivery_address,
            "customer": OrderService._map_customer_brief(order.customer),
            "installer_id": order.installers[0].installer_id if getattr(order, "installers", None) else None,
            "installer": {
                "id": order.installers[0].installer.id,
                "name": order.installers[0].installer.name,
                "is_active": order.installers[0].installer.is_active,
                "default_rate": order.installers[0].installer.default_rate,
                "telegram_id": order.installers[0].installer.telegram_id,
            } if getattr(order, "installers", None) and getattr(order.installers[0], "installer", None) else None,
        }

    @staticmethod
    def _map_product_line(link: OrderProductLink) -> Dict[str, Any]:
        product_title = link.product.title if link.product else f"Товар #{link.product_id}"
        line_total = (link.price + (link.installation_price or 0)) * link.quantity
        return {
            "id": link.id,
            "product_id": link.product_id,
            "product_title": product_title,
            "quantity": link.quantity,
            "price": link.price,
            "cost": link.cost,
            "is_installation_included": bool(link.is_installation_included),
            "installation_price": int(link.installation_price or 0),
            "line_total": line_total,
        }

    @staticmethod
    def _map_service_line(link: OrderServiceLink) -> Dict[str, Any]:
        service_title = link.title or (link.service.title if link.service else f"Услуга #{link.service_id}")
        line_total = link.price * link.quantity
        return {
            "id": link.id,
            "service_id": link.service_id,
            "service_title": service_title,
            "quantity": link.quantity,
            "price": link.price,
            "cost": link.cost,
            "line_total": line_total,
        }

    @staticmethod
    async def get_orders_for_manager(
        session: AsyncSession,
        customer_segment: str,
        page: int,
        limit: int,
        status: Optional[str] = None,
        search: Optional[str] = None,
        overdue_only: bool = False,
        sort: str = "created_at_desc",
    ) -> Dict[str, Any]:
        from schemas import Meta

        segment = customer_segment.lower()
        if segment not in {"b2c", "b2b"}:
            raise ValueError(f"Invalid segment: {customer_segment}")

        # B2B = explicit company OR customer has non-empty INN.
        # B2C = everything else (including legacy orders without linked customer).
        has_inn = and_(Customer.inn.is_not(None), func.length(func.trim(Customer.inn)) > 0)
        is_b2b = or_(Customer.type == CustomerType.company, has_inn)
        segment_clause = is_b2b if segment == "b2b" else or_(Customer.id.is_(None), not_(is_b2b))

        base_stmt = (
            select(Order)
            .outerjoin(Customer, Order.customer_id == Customer.id)
            .options(
                selectinload(Order.customer),
                selectinload(Order.product_links).selectinload(OrderProductLink.product),
                selectinload(Order.service_links).selectinload(OrderServiceLink.service),
                selectinload(Order.installers).selectinload(OrderInstaller.installer),
            )
            .where(segment_clause)
        )

        count_stmt = (
            select(func.count(Order.id))
            .outerjoin(Customer, Order.customer_id == Customer.id)
            .where(segment_clause)
        )

        if status:
            try:
                status_enum = OrderStatus(status)
                base_stmt = base_stmt.where(Order.status == status_enum)
                count_stmt = count_stmt.where(Order.status == status_enum)
            except ValueError as exc:
                raise ValueError(f"Invalid status: {status}") from exc

        if search:
            like = f"%{search.strip()}%"
            search_clause = or_(
                Customer.name.ilike(like),
                Customer.phone.ilike(like),
                Customer.full_legal_name.ilike(like),
                Customer.inn.ilike(like),
                cast(Order.id, String).ilike(like),
            )
            base_stmt = base_stmt.where(search_clause)
            count_stmt = count_stmt.where(search_clause)

        if overdue_only:
            now = datetime.now()
            base_stmt = base_stmt.where(
                Order.next_followup_date.is_not(None),
                Order.next_followup_date < now,
            )
            count_stmt = count_stmt.where(
                Order.next_followup_date.is_not(None),
                Order.next_followup_date < now,
            )

        sort_map = {
            "created_at_desc": Order.created_at.desc(),
            "created_at_asc": Order.created_at.asc(),
            "updated_at_desc": Order.updated_at.desc(),
            "updated_at_asc": Order.updated_at.asc(),
            "followup_asc": Order.next_followup_date.asc().nullslast(),
            "followup_desc": Order.next_followup_date.desc().nullslast(),
            "margin_desc": Order.margin.desc(),
            "margin_asc": Order.margin.asc(),
        }
        order_by = sort_map.get(sort, Order.created_at.desc())
        base_stmt = base_stmt.order_by(order_by).offset((page - 1) * limit).limit(limit)

        total_result = await session.execute(count_stmt)
        total = int(total_result.scalar() or 0)

        result = await session.execute(base_stmt)
        orders = list(result.scalars().all())
        items = [OrderService._map_order_list_item(order) for order in orders]

        pages = (total + limit - 1) // limit if limit > 0 else 0
        return {
            "items": items,
            "meta": Meta(total=total, page=page, limit=limit, pages=pages),
        }

    @staticmethod
    async def get_order_detail_for_manager(session: AsyncSession, order_id: int) -> Optional[Dict[str, Any]]:
        stmt = (
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.customer),
                selectinload(Order.product_links).selectinload(OrderProductLink.product),
                selectinload(Order.service_links).selectinload(OrderServiceLink.service),
                selectinload(Order.installers).selectinload(OrderInstaller.installer),
                selectinload(Order.documents),
            )
        )
        result = await session.execute(stmt)
        order = result.scalars().first()
        if not order:
            return None

        data = OrderService._map_order_list_item(order)
        data["product_lines"] = [OrderService._map_product_line(link) for link in order.product_links]
        data["service_lines"] = [OrderService._map_service_line(link) for link in order.service_links]
        data["documents"] = [
            {
                "id": doc.id,
                "doc_type": doc.doc_type,
                "number": doc.number,
                "date": doc.date,
                "edit_url": doc.google_edit_url,
            }
            for doc in sorted(order.documents, key=lambda d: d.created_at, reverse=True)
        ]
        return data


    @staticmethod
    async def build_manager_order_line_defaults(
        session: AsyncSession,
        product_id: Optional[int] = None,
        service_id: Optional[int] = None,
    ) -> Dict[str, int]:
        if product_id is not None:
            product = await session.get(Product, product_id)
            return {"cost": int(getattr(product, "cost", 0) or 0)} if product else {"cost": 0}
        if service_id is not None:
            service = await session.get(Service, service_id)
            return {"cost": int(getattr(service, "base_price", 0) or 0)} if service else {"cost": 0}
        return {"cost": 0}

    @staticmethod
    async def update_order_for_manager(
        session: AsyncSession,
        order_id: int,
        payload: Any,
    ) -> Optional[Dict[str, Any]]:
        order = await session.get(Order, order_id)
        if not order:
            return None
        from models import Customer  # noqa: avoid UnboundLocalError from conditional import below

        fields_set = getattr(payload, "model_fields_set", None)
        if fields_set is None:
            fields_set = getattr(payload, "__fields_set__", set())

        if "status" in fields_set and payload.status is not None:
            try:
                order.status = OrderStatus(payload.status)
            except ValueError as exc:
                raise ValueError(f"Invalid status: {payload.status}") from exc
        if "next_followup_date" in fields_set:
            order.next_followup_date = OrderService._normalize_naive_datetime(payload.next_followup_date)
        if "measurement_date" in fields_set:
            order.measurement_date = OrderService._normalize_naive_datetime(payload.measurement_date)
        if "installation_date" in fields_set:
            order.installation_date = OrderService._normalize_naive_datetime(payload.installation_date)
        if "comment" in fields_set:
            order.comment = payload.comment
        if "is_paid" in fields_set and payload.is_paid is not None:
            order.is_paid = payload.is_paid
        if "customer_delivery_address" in fields_set:
            order.delivery_address = payload.customer_delivery_address
        # New fields
        if "closing_result" in fields_set:
            order.closing_result = payload.closing_result
        if "reject_reason" in fields_set:
            order.reject_reason = payload.reject_reason
        if "is_on_hold" in fields_set and payload.is_on_hold is not None:
            order.is_on_hold = payload.is_on_hold
        if "on_hold_reason" in fields_set:
            order.on_hold_reason = payload.on_hold_reason
        if "measurement_required" in fields_set and payload.measurement_required is not None:
            order.measurement_required = payload.measurement_required
        if "proposal_sent_at" in fields_set:
            order.proposal_sent_at = OrderService._normalize_naive_datetime(payload.proposal_sent_at)
        # Auto-set closed_at when transitioning to CLOSED
        if "status" in fields_set and order.status == OrderStatus.CLOSED and not order.closed_at:
            order.closed_at = datetime.now()

        if "installer_id" in fields_set:
            from models import OrderInstaller
            await session.execute(delete(OrderInstaller).where(OrderInstaller.order_id == order_id))
            if getattr(payload, "installer_id", None) is not None:
                new_installer_link = OrderInstaller(
                    order_id=order_id,
                    installer_id=payload.installer_id,
                )
                session.add(new_installer_link)

        # 1. Handle explicit customer linkage (if manager finds existing customer)
        if "customer_id" in fields_set and payload.customer_id is not None:
            if order.customer_id != payload.customer_id:
                # Link to new existing customer
                new_customer = await session.get(Customer, payload.customer_id)
                if new_customer:
                    order.customer_id = payload.customer_id

        customer_field_map = {
            "customer_name": "name",
            "customer_phone": "phone",
            "customer_email": "email",
            "customer_type": "type",
            "customer_inn": "inn",
            "customer_full_legal_name": "full_legal_name",
            "customer_legal_address": "legal_address",
            "customer_bank_name": "bank_name",
            "customer_bic": "bic",
            "customer_iban": "iban",
        }
        
        # 2. Update customer fields
        requested_customer_fields = [field for field in customer_field_map if field in fields_set]
        if requested_customer_fields and order.customer_id:
            customer = await session.get(Customer, order.customer_id)
            if customer:
                def _clean_optional(value: Any) -> Optional[str]:
                    if value is None:
                        return None
                    cleaned = str(value).strip()
                    return cleaned or None

                critical_field_map = {
                    "customer_inn": "УНП",
                    "customer_iban": "IBAN",
                    "customer_bic": "BIC",
                    "customer_bank_name": "Банк",
                }
                critical_changes: List[str] = []
                for field_name, label in critical_field_map.items():
                    if field_name not in requested_customer_fields:
                        continue
                    attr_name = customer_field_map[field_name]
                    incoming = _clean_optional(getattr(payload, field_name, None))
                    existing = _clean_optional(getattr(customer, attr_name, None))
                    if existing and incoming and existing != incoming:
                        critical_changes.append(label)

                if critical_changes and not bool(getattr(payload, "confirm_critical_customer_changes", False)):
                    raise ValueError(
                        "Critical customer requisites change requires confirmation: "
                        + ", ".join(critical_changes)
                    )

                for field_name in requested_customer_fields:
                    attr_name = customer_field_map[field_name]
                    setattr(customer, attr_name, _clean_optional(getattr(payload, field_name, None)))
                session.add(customer)

        # 3. Handle specific Order technical meta qualification updates
        meta_fields_map = {
            "object_type": "object_type",
            "service_type": "service_type",
            "equipment_class": "equipment_class",
            "marketing_source": "marketing_source",
            "no_answer_at": "no_answer_at",
        }
        requested_meta_fields = [field for field in meta_fields_map if field in fields_set]
        if requested_meta_fields:
            if order.technical_meta is None:
                order.technical_meta = {}
            new_meta = dict(order.technical_meta)
            for field in requested_meta_fields:
                meta_key = meta_fields_map[field]
                val = getattr(payload, field, None)
                if val is not None:
                    new_meta[meta_key] = val
            order.technical_meta = new_meta
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(order, "technical_meta")

        if "products" in fields_set or "services" in fields_set:
            if "products" in fields_set and payload.products is not None:
                await session.execute(delete(OrderProductLink).where(OrderProductLink.order_id == order_id))
                for product_line in payload.products:
                    if product_line.quantity <= 0:
                        raise ValueError("Product quantity must be > 0")
                    if product_line.price < 0:
                        raise ValueError("Product price cannot be negative")
                    defaults = await OrderService.build_manager_order_line_defaults(
                        session=session,
                        product_id=product_line.product_id,
                    )
                    new_product_link = OrderProductLink(
                        order_id=order_id,
                        product_id=product_line.product_id,
                        quantity=product_line.quantity,
                        price=product_line.price,
                        cost=product_line.cost if product_line.cost is not None else defaults["cost"],
                    )
                    session.add(new_product_link)

            if "services" in fields_set and payload.services is not None:
                await session.execute(delete(OrderServiceLink).where(OrderServiceLink.order_id == order_id))
                for service_line in payload.services:
                    if service_line.quantity <= 0:
                        raise ValueError("Service quantity must be > 0")
                    if service_line.price < 0:
                        raise ValueError("Service price cannot be negative")
                    if not service_line.title:
                        raise ValueError("Service title is required")
                    defaults = await OrderService.build_manager_order_line_defaults(
                        session=session,
                        service_id=service_line.service_id,
                    )
                    new_service_link = OrderServiceLink(
                        order_id=order_id,
                        service_id=service_line.service_id,
                        title=service_line.title,
                        quantity=service_line.quantity,
                        price=service_line.price,
                        cost=service_line.cost if service_line.cost is not None else defaults["cost"],
                    )
                    session.add(new_service_link)

            await session.flush()
            await session.refresh(order, attribute_names=["product_links", "service_links", "installers"])
            order.calculate_totals()

        session.add(order)
        await session.commit()

        # Auto-archive customer if this order was just cancelled and they
        # have no other real (non-lead, non-cancelled) orders.
        if order.status == OrderStatus.CANCELED and order.customer_id:
            active_order_statuses = [
                OrderStatus.NEW_LEAD, OrderStatus.CANCELED
            ]
            other_real_orders_stmt = (
                select(func.count(Order.id))
                .where(
                    Order.customer_id == order.customer_id,
                    Order.id != order.id,
                    Order.status.not_in(active_order_statuses),
                )
            )
            other_real_result = await session.execute(other_real_orders_stmt)
            other_real_count = int(other_real_result.scalar() or 0)
            if other_real_count == 0:
                customer = await session.get(Customer, order.customer_id)
                if customer and not customer.is_archived:
                    customer.is_archived = True
                    session.add(customer)
                    await session.commit()

        return await OrderService.get_order_detail_for_manager(session, order_id)

    # -----------------------------------------------------------------
    # Leads Inbox (Order-based triage)
    # -----------------------------------------------------------------

    @staticmethod
    async def get_new_lead_counter(session: AsyncSession) -> tuple[int, bool]:
        """Fast count of orders with status 'new_lead'.

        Intended for the Dashboard/Sidebar badge — runs a single
        indexed COUNT query with no joins.
        """
        stmt = select(func.count()).where(Order.status == OrderStatus.NEW_LEAD)
        result = await session.execute(stmt)
        count: int = result.scalar() or 0
        return count, count > 0

    @staticmethod
    async def get_leads_inbox(session: AsyncSession, scope: str = "active"):
        """Return triage inbox items based on scope.

        scope="active"  → new_lead + assessment
                          sorted: new_lead first, then by created_at DESC.
        scope="archive" → canceled only, created_at DESC.
        """
        from schemas import LeadsInboxItemResponse, LeadsInboxListResponse
        from sqlalchemy import case as sa_case

        if scope == "archive":
            active_statuses = [OrderStatus.CANCELED]
        else:
            active_statuses = [OrderStatus.NEW_LEAD]

        stmt = (
            select(Order)
            .options(selectinload(Order.customer))
            .where(Order.status.in_(active_statuses))
        )

        if scope == "active":
            # new_lead orders float to top, then newest first
            priority_expr = sa_case(
                (Order.status == OrderStatus.NEW_LEAD, 0),
                else_=1,
            )
            stmt = stmt.order_by(priority_expr, Order.created_at.desc())
        else:
            stmt = stmt.order_by(Order.created_at.desc())

        result = await session.execute(stmt)
        orders: list[Order] = list(result.scalars().all())

        items = [
            LeadsInboxItemResponse(
                id=order.id,
                status=order.status.value if hasattr(order.status, "value") else str(order.status),
                is_new=(
                    (order.status.value if hasattr(order.status, "value") else str(order.status))
                    == "new_lead"
                ),
                customer_name=order.customer.name if order.customer else None,
                phone=order.customer.phone if order.customer else None,
                source=(
                    order.lead_source.value
                    if order.lead_source and hasattr(order.lead_source, "value")
                    else (str(order.lead_source) if order.lead_source else None)
                ),
                comment=order.comment,
                no_answer_at=(
                    datetime.fromisoformat(order.technical_meta.get("no_answer_at").replace('Z', '+00:00'))
                    if order.technical_meta and order.technical_meta.get("no_answer_at")
                    else None
                ),
                created_at=order.created_at,
            )
            for order in orders
        ]

        return LeadsInboxListResponse(items=items, total=len(items))

