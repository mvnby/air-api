import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/ha/check_ha_external_prerequisites.py"


spec = importlib.util.spec_from_file_location("check_ha_external_prerequisites", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _metadata(*, variables: dict[str, str] | None = None, secrets: set[str] | None = None):
    return module.GithubMetadata(variables=variables or {}, secrets=secrets or set())


def test_external_prerequisites_report_missing_cloudflare_secret_and_vars():
    ok, warnings, failures = module.check_metadata(
        _metadata(
            variables={
                "API_HA_READINESS_STRICT": "false",
                "CLOUDFLARE_LB_CONFIG_REQUIRED": "false",
                "POSTGRES_PITR_MAX_BASEBACKUP_AGE_HOURS": "30",
                "POSTGRES_PITR_MAX_WAL_AGE_MINUTES": "180",
                "POSTGRES_PITR_REQUIRED": "false",
            },
            secrets=set(),
        ),
        require_strict=False,
    )

    assert any("missing GitHub secret CLOUDFLARE_LB_READ_TOKEN" in item for item in failures)
    assert any("missing GitHub variable CLOUDFLARE_ACCOUNT_ID" in item for item in failures)
    assert any("missing GitHub variable CLOUDFLARE_ZONE_ID" in item for item in failures)
    assert any("missing optional GitHub secret HA_ALERT_TELEGRAM_BOT_TOKEN" in item for item in warnings)
    assert any("missing optional GitHub secret HA_ALERT_TELEGRAM_CHAT_ID" in item for item in warnings)
    assert any("POSTGRES_PITR_REQUIRED is not true yet" in item for item in warnings)
    assert any("variable present: POSTGRES_PITR_MAX_WAL_AGE_MINUTES" in item for item in ok)


def test_external_prerequisites_require_strict_fails_when_flags_are_false():
    ok, warnings, failures = module.check_metadata(
        _metadata(
            variables={
                "API_HA_READINESS_STRICT": "false",
                "CLOUDFLARE_ACCOUNT_ID": "account",
                "CLOUDFLARE_LB_CONFIG_REQUIRED": "false",
                "CLOUDFLARE_ZONE_ID": "zone",
                "POSTGRES_PITR_MAX_BASEBACKUP_AGE_HOURS": "30",
                "POSTGRES_PITR_MAX_WAL_AGE_MINUTES": "180",
                "POSTGRES_PITR_REQUIRED": "false",
            },
            secrets={"CLOUDFLARE_LB_READ_TOKEN"},
        ),
        require_strict=True,
    )

    assert any("API_HA_READINESS_STRICT must be true" in item for item in failures)
    assert any("CLOUDFLARE_LB_CONFIG_REQUIRED must be true" in item for item in failures)
    assert any("POSTGRES_PITR_REQUIRED must be true" in item for item in failures)
    assert any("secret present: CLOUDFLARE_LB_READ_TOKEN" in item for item in ok)
    assert any("private PITR R2 credentials are host-local" in item for item in warnings)


def test_external_prerequisites_pass_when_all_metadata_is_ready():
    ok, warnings, failures = module.check_metadata(
        _metadata(
            variables={
                "API_HA_READINESS_STRICT": "true",
                "CLOUDFLARE_ACCOUNT_ID": "account",
                "CLOUDFLARE_LB_CONFIG_REQUIRED": "true",
                "CLOUDFLARE_ZONE_ID": "zone",
                "POSTGRES_PITR_MAX_BASEBACKUP_AGE_HOURS": "30",
                "POSTGRES_PITR_MAX_WAL_AGE_MINUTES": "180",
                "POSTGRES_PITR_REQUIRED": "true",
            },
            secrets={"CLOUDFLARE_LB_READ_TOKEN", "HA_ALERT_TELEGRAM_BOT_TOKEN", "HA_ALERT_TELEGRAM_CHAT_ID"},
        ),
        require_strict=True,
    )

    assert not failures
    assert any("optional secret present: HA_ALERT_TELEGRAM_BOT_TOKEN" in item for item in ok)
    assert any("strict variable enabled: API_HA_READINESS_STRICT" in item for item in ok)
    assert any("strict variable enabled: POSTGRES_PITR_REQUIRED" in item for item in ok)
    assert any("private PITR R2 credentials are host-local" in item for item in warnings)
