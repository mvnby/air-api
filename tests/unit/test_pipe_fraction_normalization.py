import pytest

from services.spec_normalizer import normalize_specs


@pytest.mark.parametrize("fraction", ["1/4", "3/8", "1/2", "5/8", "3/4"])
def test_unquoted_catalog_pipe_fractions_keep_the_denominator(fraction):
    specs = normalize_specs({"pipe_liquid": fraction, "pipe_gas": fraction})

    for key in ("pipe_liquid", "pipe_gas"):
        assert specs[key] == f'{fraction}"'
        assert specs["__typed_specs"][key]["value"] == f'{fraction}"'


def test_pipe_fraction_normalization_is_idempotent_and_keeps_metric_conversion():
    original = {"pipe_liquid": "1 / 4", "pipe_gas": "9,52 (3/8)"}
    once = normalize_specs(original)

    assert once["pipe_liquid"] == '1/4"'
    assert once["pipe_gas"] == '3/8"'
    assert normalize_specs(once) == once
