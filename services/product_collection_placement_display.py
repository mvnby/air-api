"""Presentation is applied only after the canonical resolver's minimum/fallback policy."""
from api_contracts.product_collections import ProductCollectionPlacementDisplayConfig


def display_config(placement=None) -> dict:
    if placement is None:
        return ProductCollectionPlacementDisplayConfig().model_dump()
    return {
        field: getattr(placement, field)
        for field in ProductCollectionPlacementDisplayConfig.model_fields
    }


def present_items(items: list[dict], config: dict, *, day: int) -> list[dict]:
    pool = items[:config["item_limit"]] if config["item_limit"] is not None else items
    if config["display_mode"] == "single" and pool:
        index = day % len(pool) if config["rotation_mode"] == "daily" else 0
        pool = [pool[index]]
    return [{**item, "position": position} for position, item in enumerate(pool)]


def select_daily_collections(collections: list[dict], *, day: int) -> list[dict]:
    candidates = [
        index for index, row in enumerate(collections)
        if row["display_mode"] == "single" and row["rotation_mode"] == "daily"
    ]
    if not candidates:
        return collections
    chosen = candidates[day % len(candidates)]
    return [row for index, row in enumerate(collections) if index not in candidates or index == chosen]


def present_collections(collections: list[dict], *, day: int) -> list[dict]:
    daily_count = sum(
        row["display_mode"] == "single" and row["rotation_mode"] == "daily"
        for row in collections
    )
    displayed = []
    for row in select_daily_collections(collections, day=day):
        # Advance the product once per appearance of its collection. Using the
        # same day modulo both pool sizes can permanently starve some products.
        appearance = (
            day // daily_count
            if row["display_mode"] == "single" and row["rotation_mode"] == "daily"
            else day
        )
        displayed.append({**row, "items": present_items(row["items"], row, day=appearance)})
    return displayed
