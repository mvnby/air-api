from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/ha/create_postgres_pitr_basebackup.sh"


def test_basebackup_uses_db_container_network_namespace():
    script = SCRIPT.read_text(encoding="utf-8")

    assert '--network "container:${db_container}"' in script
    assert '-e PGHOST="127.0.0.1"' in script
    assert '--network "${network}"' not in script
    assert 'docker inspect -f' not in script
