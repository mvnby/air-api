from pathlib import Path


def test_bot_handlers_do_not_use_direct_db_queries():
    handlers_dir = Path("bot_app/handlers")
    for path in handlers_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "from sqlmodel import select" not in source, f"{path} imports select directly"
        assert "session.execute(" not in source, f"{path} executes SQL directly"
        assert "from crud." not in source, f"{path} imports CRUD directly"


def test_bot_handlers_resolve_staff_access_only_through_bot_provider():
    handlers_dir = Path("bot_app/handlers")
    forbidden_imports = (
        "services.bot_access_service",
        "services.staff_user_service",
    )
    for path in handlers_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_imports:
            assert forbidden not in source, f"{path} bypasses bot access provider: {forbidden}"


def test_bot_http_gateway_does_not_import_backend_runtime_layers():
    source = Path("bot_app/api_gateway.py").read_text(encoding="utf-8")
    forbidden_imports = (
        "from core.database",
        "from models",
        "from crud",
        "from services",
    )
    for forbidden in forbidden_imports:
        assert forbidden not in source, f"HTTP gateway imports backend layer: {forbidden}"


def test_bot_catalog_search_path_uses_api_instead_of_product_service_reads():
    source = Path("bot_app/handlers/catalog.py").read_text(encoding="utf-8")
    assert "ProductService.search_products" not in source
    assert "ProductService.get_by_id" not in source
    assert "get_bot_api_gateway().search_catalog" in source
    assert "get_bot_api_gateway().get_catalog_product" in source


def test_bot_catalog_presenter_does_not_import_backend_services():
    source = Path("bot_app/catalog_presenter.py").read_text(encoding="utf-8")
    for forbidden in ("from core.database", "from models", "from crud", "from services"):
        assert forbidden not in source, f"catalog presenter imports backend layer: {forbidden}"


def test_bot_task_read_paths_use_api_instead_of_task_service_reads():
    for filename in ("work.py", "admin.py"):
        source = Path(f"bot_app/handlers/{filename}").read_text(encoding="utf-8")
        assert "BotTaskService.list_my_tasks" not in source
        assert "get_bot_api_gateway().list_my_tasks" in source


def test_bot_task_mutation_paths_use_api_instead_of_backend_task_service():
    source = Path("bot_app/handlers/work.py").read_text(encoding="utf-8")
    assert "BotTaskService" not in source
    assert "get_bot_api_gateway().update_task_status" in source
    assert "get_bot_api_gateway().save_task_report" in source


def test_bot_task_presenter_does_not_import_backend_runtime_layers():
    source = Path("bot_app/task_presenter.py").read_text(encoding="utf-8")
    for forbidden in ("from core.database", "from models", "from crud", "from services"):
        assert forbidden not in source, f"task presenter imports backend layer: {forbidden}"


def test_bot_quick_order_paths_use_api_instead_of_backend_service():
    source = Path("bot_app/handlers/work.py").read_text(encoding="utf-8")
    assert "BotQuickOrderService" not in source
    assert "get_bot_api_gateway().parse_quick_order" in source
    assert "get_bot_api_gateway().create_quick_order" in source


def test_bot_customer_requisites_paths_use_api_instead_of_backend_service():
    source = Path("bot_app/handlers/admin.py").read_text(encoding="utf-8")
    assert "CustomerRequisitesRecognitionService" not in source
    assert "get_bot_api_gateway().recognize_customer_requisites_file" in source
    assert "get_bot_api_gateway().recognize_customer_requisites_text" in source
    assert "get_bot_api_gateway().apply_customer_requisites_action" in source


def test_bot_quick_order_presenter_does_not_import_backend_runtime_layers():
    source = Path("bot_app/quick_order_presenter.py").read_text(encoding="utf-8")
    for forbidden in ("from core.database", "from models", "from crud", "from services"):
        assert forbidden not in source, f"quick-order presenter imports backend layer: {forbidden}"
