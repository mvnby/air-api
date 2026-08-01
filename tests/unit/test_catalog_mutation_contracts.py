from __future__ import annotations

import ast
from pathlib import Path

from services.catalog_mutation_contracts import (
    FEATURE_DELETE_GLOBAL_MUTATION_PRODUCERS,
    GLOBAL_CATALOG_MUTATION_CONTRACTS,
    IMPORTER_GLOBAL_MUTATION_PRODUCERS,
    MANAGER_MEDIA_GLOBAL_MUTATION_PRODUCERS,
    PUBLIC_CATALOG_MUTATION_ENTRYPOINTS,
    PUBLIC_CATALOG_MUTATION_PRODUCERS,
)


ROOT = Path(__file__).resolve().parents[2]
TRANSACTION_OWNER_PATHS = (
    ROOT / "services/importer_service.py",
    ROOT / "services/manager_media_service.py",
    ROOT / "services/manager_media_storage_service.py",
)


def test_public_catalog_mutation_inventory_covers_reviewed_entrypoints():
    assert set(PUBLIC_CATALOG_MUTATION_ENTRYPOINTS) == {
        "ImporterService.import_product",
        "ManagerMediaService.set_main_image",
        "ManagerMediaService.delete_gallery_image",
        "ManagerMediaService.crop_gallery_image",
        "ManagerMediaService.remove_background_gallery_image",
        "ManagerMediaService.reuse_image_link",
        "ManagerMediaService.process_and_save_image",
        "ManagerMediaService.save_image_from_bytes",
        "ManagerMediaService.save_images_from_bytes",
        "ManagerMediaService.bulk_add_gallery_images",
        "ManagerMediaService.bulk_delete_common_gallery_images",
        "ManagerMediaService.apply_gallery_to_series",
        "ManagerMediaService.bulk_upload_local_images",
        "ManagerMediaOrchestratorService.upload_image_from_url",
        "ManagerMediaOrchestratorService.upload_local_images",
        "ManagerMediaOrchestratorService.link_search_result",
        "ManagerMediaOrchestratorService.bulk_upload_local_images",
        "FeatureAssignmentService.delete_product_assignment",
        "FeatureAssignmentService.delete_target_link",
    }

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
    )


def test_catalog_transaction_owners_never_commit_around_the_invalidation_boundary():
    offenders: list[str] = []
    for path in TRANSACTION_OWNER_PATHS:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr == "commit":
                offenders.append(f"{path.name}:{node.lineno}")

    assert offenders == []


def test_literal_registered_producers_exist_in_the_contract_inventory():
    literal_producers: set[str] = set()
    for path in (*TRANSACTION_OWNER_PATHS, ROOT / "services/feature_assignment_service.py"):
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


def test_manager_media_facade_stays_below_the_monolith_limit():
    facade = ROOT / "services/manager_media_service.py"
    assert len(facade.read_text().splitlines()) < 700
