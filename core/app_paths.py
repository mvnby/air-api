from pathlib import Path


def get_base_dir() -> str:
    return str(Path(__file__).resolve().parent.parent)


def get_manager_dist(base_dir: str) -> str:
    return str(Path(base_dir) / "manager_frontend" / "dist")
