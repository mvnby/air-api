from pathlib import Path


def get_base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def get_manager_dist(base_dir: Path) -> Path:
    return base_dir / "manager_frontend" / "dist"
