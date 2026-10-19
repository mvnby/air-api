"""Shared fallback for features whose presentation has not been authored."""


def feature_display_mode(mode: str | None, *, is_featured: bool = False) -> str:
    return mode or ("detailed" if is_featured else "icon")
