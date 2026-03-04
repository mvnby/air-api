from pathlib import Path


def test_bot_handlers_do_not_use_direct_db_queries():
    handlers_dir = Path("bot_app/handlers")
    for path in handlers_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "from sqlmodel import select" not in source, f"{path} imports select directly"
        assert "session.execute(" not in source, f"{path} executes SQL directly"
        assert "from crud." not in source, f"{path} imports CRUD directly"
