from __future__ import annotations

import ast
from pathlib import Path

from services.catalog_mutation_contracts import (
    FEATURE_DELETE_GLOBAL_MUTATION_PRODUCERS,
    FEATURE_MIGRATION_GLOBAL_MUTATION_PRODUCERS,
    GLOBAL_CATALOG_MUTATION_CONTRACTS,
    IMPORTER_GLOBAL_MUTATION_PRODUCERS,
    MANAGER_BRAND_GLOBAL_MUTATION_PRODUCERS,
    MANAGER_MEDIA_GLOBAL_MUTATION_PRODUCERS,
    PRODUCT_IMAGE_VARIANT_GLOBAL_MUTATION_PRODUCERS,
    PUBLIC_CATALOG_MUTATION_ENTRYPOINTS,
    PUBLIC_CATALOG_MUTATION_PRODUCERS,
)
from tests.unit.catalog_mutation_route_scanner import (
    ScopedServiceCall,
    scan_command_service_calls,
    scan_route_service_calls,
    unresolved_service_entrypoints,
)


ROOT = Path(__file__).resolve().parents[2]
SCOPED_MUTATION_ROUTER_PATHS = (
    ROOT / "routers/manager_media_gallery_write.py",
    ROOT / "routers/manager_media_ingest_write.py",
    ROOT / "routers/manager_brands.py",
)
SCOPED_COMMAND_CALLER_PATHS = (
    ROOT / "scripts/backfill_yandex_feed_images.py",
)
NESTED_CATALOG_MUTATION_METHODS = {
    "bulk_add_gallery_images",
    "reprocess_variant",
}


def _module_path(module: str) -> Path:
    return ROOT.joinpath(*module.split(".")).with_suffix(".py")


def _imported_symbols(path: Path) -> dict[str, Path]:
    imported: dict[str, Path] = {}
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        module_path = _module_path(node.module)
        if not module_path.exists():
            continue
        for alias in node.names:
            imported[alias.asname or alias.name] = module_path
    return imported


def _scoped_service_calls() -> tuple[ScopedServiceCall, ...]:
    return (
        *scan_route_service_calls(SCOPED_MUTATION_ROUTER_PATHS),
        *scan_command_service_calls(SCOPED_COMMAND_CALLER_PATHS),
    )


def _has_false_commit_keyword(node: ast.Call) -> bool:
    return any(
        keyword.arg == "commit"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is False
        for keyword in node.keywords
    )


def _transaction_owner_paths() -> tuple[Path, ...]:
    """Discover route owners, inherited operations, and nested callers."""

    paths = {
        ROOT / "services/importer_service.py",
        *SCOPED_MUTATION_ROUTER_PATHS,
        *SCOPED_COMMAND_CALLER_PATHS,
    }
    for caller_path in (*SCOPED_MUTATION_ROUTER_PATHS, *SCOPED_COMMAND_CALLER_PATHS):
        imports = _imported_symbols(caller_path)
        for call in _scoped_service_calls():
            if call.source != caller_path.name:
                continue
            class_name = call.entrypoint.split(".", 1)[0]
            paths.add(imports[class_name])

    for path in (ROOT / "services").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in NESTED_CATALOG_MUTATION_METHODS
                and _has_false_commit_keyword(node)
            ):
                paths.add(path)

    pending = list(paths)
    while pending:
        path = pending.pop()
        if path.parent.name != "services":
            continue
        imports = _imported_symbols(path)
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id in imports:
                    inherited_path = imports[base.id]
                    if inherited_path not in paths:
                        paths.add(inherited_path)
                        pending.append(inherited_path)

    return tuple(sorted(paths))


def test_public_catalog_mutation_inventory_covers_reviewed_entrypoints():
    entrypoint_producers = {
        producer
        for producers in PUBLIC_CATALOG_MUTATION_ENTRYPOINTS.values()
        for producer in producers
    }
    assert entrypoint_producers == set(PUBLIC_CATALOG_MUTATION_PRODUCERS)
    assert set(GLOBAL_CATALOG_MUTATION_CONTRACTS) == set(
        IMPORTER_GLOBAL_MUTATION_PRODUCERS
        | MANAGER_MEDIA_GLOBAL_MUTATION_PRODUCERS
        | FEATURE_DELETE_GLOBAL_MUTATION_PRODUCERS
        | FEATURE_MIGRATION_GLOBAL_MUTATION_PRODUCERS
        | PRODUCT_IMAGE_VARIANT_GLOBAL_MUTATION_PRODUCERS
        | MANAGER_BRAND_GLOBAL_MUTATION_PRODUCERS
    )


def test_catalog_transaction_owners_never_commit_around_the_invalidation_boundary():
    offenders: list[str] = []
    for path in _transaction_owner_paths():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr == "commit":
                offenders.append(f"{path.name}:{node.lineno}")

    assert offenders == []


def test_literal_registered_producers_exist_in_the_contract_inventory():
    literal_producers: set[str] = set()
    paths = {
        *_transaction_owner_paths(),
        ROOT / "services/feature_assignment_service.py",
    }
    for path in paths:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "commit_registered_global_mutation":
                continue
            producer_keyword = next(
                (keyword for keyword in node.keywords if keyword.arg == "producer"),
                None,
            )
            if producer_keyword and isinstance(producer_keyword.value, ast.Constant):
                literal_producers.add(str(producer_keyword.value.value))

    assert literal_producers
    assert literal_producers <= set(GLOBAL_CATALOG_MUTATION_CONTRACTS)
    scoped_producers = {
        producer
        for call in _scoped_service_calls()
        for producer in PUBLIC_CATALOG_MUTATION_ENTRYPOINTS[call.entrypoint]
    }
    assert scoped_producers <= literal_producers


def test_scoped_routes_and_command_callers_are_registered_automatically():
    registered = set(PUBLIC_CATALOG_MUTATION_ENTRYPOINTS)
    missing = [
        f"{call.source}:{call.owner}:{call.transport}:{call.entrypoint}"
        for call in _scoped_service_calls()
        if call.entrypoint not in registered
    ]
    assert missing == []


def test_registered_entrypoints_resolve_to_real_service_methods():
    assert unresolved_service_entrypoints(
        ROOT / "services",
        PUBLIC_CATALOG_MUTATION_ENTRYPOINTS,
    ) == set()


def test_nested_catalog_mutations_require_a_caller_owned_batch():
    offenders: list[str] = []
    for path in (ROOT / "services").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in NESTED_CATALOG_MUTATION_METHODS:
                continue
            if not _has_false_commit_keyword(node):
                continue
            if not any(keyword.arg == "mutation_batch" for keyword in node.keywords):
                offenders.append(f"{path.name}:{node.lineno}")

    assert offenders == []


def test_manager_media_request_paths_never_unlink_physical_objects():
    paths = {
        *SCOPED_MUTATION_ROUTER_PATHS,
        *(ROOT / "routers").glob("manager_media*.py"),
        *(ROOT / "services").glob("manager_media*.py"),
    }
    offenders: list[str] = []
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            is_os_remove = (
                node.func.attr == "remove"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
            )
            if node.func.attr in {"unlink", "remove_file_if_unreferenced"} or is_os_remove:
                offenders.append(f"{path.name}:{node.lineno}")

    assert offenders == []


def test_manager_media_facade_stays_below_the_monolith_limit():
    manager_files = (
        ROOT / "services/manager_media_service.py",
        ROOT / "services/manager_brand_service.py",
        ROOT / "services/manager_brand_series_service.py",
    )
    assert {
        path.name: len(path.read_text().splitlines())
        for path in manager_files
        if len(path.read_text().splitlines()) >= 700
    } == {}
