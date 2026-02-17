from main import app
from routers.manager_operation_ids import ALL_MANAGER_OPERATION_IDS


def test_manager_operation_ids_match_openapi():
    schema = app.openapi()
    manager_openapi_ids = set()

    for path, methods in schema.get("paths", {}).items():
        if not path.startswith("/api/manager"):
            continue
        for method, operation in methods.items():
            if method.lower() not in {"get", "post", "patch", "put", "delete"}:
                continue
            operation_id = operation.get("operationId")
            assert operation_id, f"Missing operationId for {method.upper()} {path}"
            manager_openapi_ids.add(operation_id)

    expected_ids = set(ALL_MANAGER_OPERATION_IDS)
    assert manager_openapi_ids == expected_ids
