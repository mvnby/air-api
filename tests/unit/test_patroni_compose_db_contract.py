import copy

import pytest

from scripts.ha.patroni_compose_db_contract import ContractError, contract_digest


def _config() -> dict:
    return {
        "name": "mvn-api",
        "services": {
            "db": {
                "image": "${PATRONI_IMAGE}",
                "networks": {"default": None},
                "volumes": [
                    {
                        "source": "postgres_data",
                        "target": "/var/lib/postgresql/data",
                        "type": "volume",
                    },
                    {
                        "source": "/srv/wal",
                        "target": "/archive",
                        "type": "bind",
                    },
                ],
            }
        },
        "networks": {"default": {"name": "mvn-api_default"}},
        "volumes": {
            "postgres_data": {"external": True, "name": "air-api_postgres_data"}
        },
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(name="other-project"),
        lambda value: value["services"]["db"].update(image="${BACKEND_IMAGE}"),
        lambda value: value["volumes"]["postgres_data"].update(
            name="other-postgres-data"
        ),
        lambda value: value["networks"]["default"].update(name="other-network"),
    ],
)
def test_contract_digest_covers_db_project_and_referenced_resources(mutation):
    canonical = _config()
    candidate = copy.deepcopy(canonical)
    mutation(candidate)

    assert contract_digest(candidate) != contract_digest(canonical)


def test_contract_digest_ignores_resources_not_referenced_by_db():
    canonical = _config()
    candidate = copy.deepcopy(canonical)
    candidate["volumes"]["app_cache"] = {"name": "mvn-api-app-cache"}

    assert contract_digest(candidate) == contract_digest(canonical)


def test_contract_rejects_missing_referenced_resource():
    value = _config()
    value["volumes"].clear()

    with pytest.raises(ContractError, match="undefined volumes"):
        contract_digest(value)
