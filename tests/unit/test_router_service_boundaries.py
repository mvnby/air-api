from pathlib import Path


def test_refactored_routers_do_not_perform_direct_db_work():
    repo_root = Path(__file__).resolve().parents[2]
    router_paths = [
        repo_root / "routers" / "manager_orders_write.py",
        repo_root / "routers" / "manager_calendar.py",
    ]
    forbidden = (
        "async_session_maker",
        "session.add",
        "session.commit",
        "session.delete",
        "session.execute",
        "select(",
    )

    for path in router_paths:
        source = path.read_text()
        for token in forbidden:
            assert token not in source, f"{path.name} contains direct DB token {token!r}"
