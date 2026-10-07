import pytest

from api_contracts.public_catalog import PublicProductSearchItemResponse
from schemas import ProductListResponse, ProductResponse, ProductSiblingResponse
from services.product_identity import public_product_identity
from services.spec_normalizer import normalize_specs


@pytest.mark.parametrize("raw, expected", [("07", "07"), (9, "09"), (" 12 ", "12"), ("48", "48"), (None, None), (True, None), (9.0, None), ("9000 BTU/h", None), ("2.6 кВт", None), ("09/12", None), ("00", None), ({}, None)])
def test_explicit_nominal_class_normalization(raw, expected):
    specs = normalize_specs({"Модель": "TAC-09CHSD/ZG11IHB", "Класс мощности": raw}, auto_tag_slugs=[])
    assert public_product_identity(specs) == {"model_code": "TAC-09CHSD/ZG11IHB", "capacity_class": expected}
    assert normalize_specs(specs, auto_tag_slugs=[]) == specs


def test_identity_does_not_infer_from_model_or_power():
    specs = normalize_specs({"model_code": "KWH09ACC-S6DBA2A", "Мощность охлаждения": "2.6 кВт"}, title="KINGHOME Prestige KWH09ACC-S6DBA2A", auto_tag_slugs=[])
    assert public_product_identity(specs) == {"model_code": "KWH09ACC-S6DBA2A", "capacity_class": None}
    for raw in [None, [], {"model": 123}, {"model": "  "}]:
        assert public_product_identity(raw) == {"model_code": None, "capacity_class": None}


@pytest.mark.parametrize("schema", [ProductResponse, ProductListResponse, ProductSiblingResponse, PublicProductSearchItemResponse])
def test_public_identity_schema_is_nullable_string(schema):
    properties = schema.model_json_schema()["properties"]
    for key in ("model_code", "capacity_class"):
        assert properties[key]["anyOf"] == [{"type": "string"}, {"type": "null"}]
        assert properties[key]["default"] is None
