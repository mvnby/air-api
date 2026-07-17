import ast
from pathlib import Path

import yaml


BOT_COMPOSE_PATHS = (
    "docker-compose.yml",
    "docker-compose.api.yml",
    "docker-compose.prod.yml",
    "deploy/ha/mvn-api/docker-compose.patroni.yml",
    "deploy/ha/mvn-api/docker-compose.primary.yml",
    "deploy/ha/mvn-api/docker-compose.standby.yml",
    "deploy/ha/zakup/docker-compose.patroni.yml",
    "deploy/ha/zakup/docker-compose.primary.yml",
    "deploy/ha/zakup/docker-compose.standby.yml",
)
PRODUCTION_BOT_COMPOSE_PATHS = tuple(
    path
    for path in BOT_COMPOSE_PATHS
    if path == "docker-compose.prod.yml" or path.startswith("deploy/ha/")
)
BOT_ALLOWED_ENVIRONMENT = {
    "APP_ROLE",
    "BOT_API_BASE_URL",
    "BOT_API_TIMEOUT_SECONDS",
    "BOT_API_TOKEN",
    "BOT_DROP_PENDING_UPDATES",
    "BOT_ENABLED",
    "BOT_RUNTIME_LEASE_SECONDS",
    "BOT_RUNTIME_RENEW_SECONDS",
    "BOT_RUNTIME_RETRY_SECONDS",
    "BOT_TOKEN",
    "ENVIRONMENT",
    "MANAGER_BASE_URL",
    "PUBLIC_API_BASE",
    "PUBLIC_SITE_URL",
}


def test_bot_handlers_do_not_use_direct_db_queries():
    handlers_dir = Path("bot_app/handlers")
    for path in handlers_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "from sqlmodel import select" not in source, f"{path} imports select directly"
        assert "session.execute(" not in source, f"{path} executes SQL directly"
        assert "from crud." not in source, f"{path} imports CRUD directly"


def test_entire_bot_package_has_no_monolith_runtime_imports():
    forbidden_roots = {"core", "models", "services", "crud", "schemas"}
    for path in Path("bot_app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                assert root not in forbidden_roots, f"{path} imports backend package {node.module}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    assert root not in forbidden_roots, f"{path} imports backend package {alias.name}"


def test_bot_compose_services_have_no_database_dependency_or_credentials():
    for compose_path in BOT_COMPOSE_PATHS:
        compose = yaml.safe_load(Path(compose_path).read_text(encoding="utf-8"))
        bot = compose["services"]["bot"]
        dependencies = bot.get("depends_on", [])
        dependency_names = set(dependencies if isinstance(dependencies, list) else dependencies)
        assert "db" not in dependency_names, compose_path
        assert "volumes" not in bot, compose_path

        env_files = bot.get("env_file", [])
        assert env_files in ([], [".ha-bot-role.env"]), compose_path

        environment = bot.get("environment", {})
        assert {"BOT_TOKEN", "BOT_API_TOKEN", "BOT_API_BASE_URL"} <= set(environment)
        assert set(environment) <= BOT_ALLOWED_ENVIRONMENT, compose_path


def test_monolith_production_bot_is_explicit_legacy_fallback_only():
    for compose_path in PRODUCTION_BOT_COMPOSE_PATHS:
        compose = yaml.safe_load(Path(compose_path).read_text(encoding="utf-8"))
        bot = compose["services"]["bot"]
        assert bot.get("profiles") == ["legacy-bot"], compose_path
        assert bot.get("restart") != "always", compose_path


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
    for filename in ("work.py", "attachments.py"):
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
    source = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in ("bot_app/handlers/admin_common.py", "bot_app/handlers/requisites.py")
    )
    assert "CustomerRequisitesRecognitionService" not in source
    assert "get_bot_api_gateway().recognize_customer_requisites_file" in source
    assert "get_bot_api_gateway().recognize_customer_requisites_text" in source
    assert "get_bot_api_gateway().apply_customer_requisites_action" in source


def test_bot_quick_order_presenter_does_not_import_backend_runtime_layers():
    source = Path("bot_app/quick_order_presenter.py").read_text(encoding="utf-8")
    for forbidden in ("from core.database", "from models", "from crud", "from services"):
        assert forbidden not in source, f"quick-order presenter imports backend layer: {forbidden}"
