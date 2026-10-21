import pytest

from services.catalog_decision_search import split_catalog_decision_search


@pytest.mark.parametrize("search", ["7 кВт", "7kw", "7 KW", "7,0 кВт", "7.0kw"])
def test_explicit_kw_is_exact_capacity_without_text_tokens(search):
    assert split_catalog_decision_search(search) == ([], (7.0,))


def test_capacity_search_preserves_brand_and_model_tokens():
    assert split_catalog_decision_search("Gree Elite 7 кВт GWH24") == (["Gree", "Elite", "GWH24"], (7.0,))


@pytest.mark.parametrize("search", ["7", "GWH7KW"])
def test_plain_numbers_and_model_names_keep_existing_search_meaning(search):
    assert split_catalog_decision_search(search) == ([search], ())


@pytest.mark.parametrize("search,expected", [("100 кВт", 100), ("125 kw", 125), ("125,5 KW", 125.5)])
def test_explicit_kw_preserves_large_nominal_scale(search, expected):
    assert split_catalog_decision_search(search) == ([], (expected,))


@pytest.mark.parametrize("search", ["GWH100KW", "TCC-125kw", "100KW-A"])
def test_kw_in_model_identifiers_is_not_a_capacity_filter(search):
    assert split_catalog_decision_search(search) == ([search], ())
