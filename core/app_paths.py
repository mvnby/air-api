from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class AppPaths:
    base_dir: Path
    manager_dist: Path


def get_base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def get_manager_dist(base_dir: Path) -> Path:
    return base_dir / "manager_frontend" / "dist"


def get_app_paths() -> AppPaths:
    base_dir = get_base_dir()
    return AppPaths(base_dir=base_dir, manager_dist=get_manager_dist(base_dir))
