import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ha import patroni_rollout_local
from scripts.ha.patroni_rollout_schema import NODE_CONTRACTS


def _rendered_config(project_root: str, alias: str) -> dict:
    contract = NODE_CONTRACTS[alias]
    return {
        "name": contract["compose_project"],
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
                        "source": project_root + "/postgres-wal-archive",
                        "target": "/postgres-wal-archive",
                        "type": "bind",
                    },
                ],
            }
        },
        "networks": {"default": {"name": contract["compose_project"] + "_default"}},
        "volumes": {
            "postgres_data": {
                "external": True,
                "name": contract["data_volume"],
            }
        },
    }


@pytest.mark.parametrize("alias", sorted(NODE_CONTRACTS))
def test_local_contract_render_is_bound_to_exact_remote_project_root_across_checkouts(
    alias, monkeypatch
):
    commands: list[list[str]] = []

    def fake_run(args, **_kwargs):
        command = list(args)
        commands.append(command)
        if "--project-directory" in command:
            project_root = command[command.index("--project-directory") + 1]
        else:
            compose_source = Path(command[command.index("-f") + 1])
            project_root = str(compose_source.parent)
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(_rendered_config(project_root, alias)),
            "",
        )

    monkeypatch.setattr(
        patroni_rollout_local, "_prove_reviewed_checkout", lambda *_args: None
    )
    monkeypatch.setattr(patroni_rollout_local.subprocess, "run", fake_run)

    digests = []
    for checkout in ("/tmp/checkout-a", "/private/tmp/checkout-b"):
        node = SimpleNamespace(
            alias=alias,
            compose_source=Path(checkout) / alias / "docker-compose.patroni.yml",
        )
        monkeypatch.setattr(patroni_rollout_local, "PATRONI_NODES", (node,))
        digests.append(patroni_rollout_local.local_contract_digests("1" * 40)[alias])

    expected_root = str(NODE_CONTRACTS[alias]["project_dir"])
    assert digests[0] == digests[1]
    assert len(commands) == 2
    for command in commands:
        project_directory = command.index("--project-directory")
        assert command[project_directory + 1] == expected_root
        assert project_directory < command.index("-f")
