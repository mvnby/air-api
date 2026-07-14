from scripts.ha import apply_postgres_pitr_primary_prerequisites as apply_pitr
from scripts.ha import configure_postgres_pitr_env as configure_pitr
from scripts.ha import run_postgres_pitr_tool as run_pitr_tool
from scripts.ha import verify_postgres_pitr_runtime as verify_pitr


REVIEWED_PRODUCTION_DESTINATION_FINGERPRINT = (
    "3c6e78da6f79b317f8b62d3f979bb69dba1f2821e473a670be30ec08310f458b"
)


def test_production_destination_fingerprint_is_literal_and_consistent():
    production_fingerprints = {
        apply_pitr.EXPECTED_DESTINATION_FINGERPRINT,
        configure_pitr.EXPECTED_DESTINATION_FINGERPRINT,
        run_pitr_tool.EXPECTED_DESTINATION_FINGERPRINT,
        verify_pitr.EXPECTED_DESTINATION_FINGERPRINT,
    }

    assert production_fingerprints == {REVIEWED_PRODUCTION_DESTINATION_FINGERPRINT}
