from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/ha/create_postgres_pitr_basebackup.sh"


def test_basebackup_uses_db_container_network_namespace():
    script = SCRIPT.read_text(encoding="utf-8")

    assert '--network "container:${db_container}"' in script
    assert '-e PGHOST="${PGHOST}"' in script
    assert '--network "${network}"' not in script
    assert 'docker inspect -f' not in script


def test_basebackup_binds_primary_lineage_before_upload():
    script = SCRIPT.read_text(encoding="utf-8")

    assert "SELECT s.system_identifier::text, c.timeline_id::text" in script
    assert '[[ "${system_identifier_after}" == "${system_identifier}"' in script
    assert '--system-identifier "${system_identifier}"' in script
    assert '--timeline "${timeline}"' in script
    assert '--start-lsn "${start_lsn}"' in script
    assert '--end-lsn "${end_lsn}"' in script
    assert '--source-node "${SOURCE_NODE}"' in script
    assert 'backup_dir="${BACKUP_ROOT}/${PITR_OPERATION_ID}"' in script
