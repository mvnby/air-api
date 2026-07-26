from types import SimpleNamespace

import pytest

from scripts.ha import patroni_role_agent


@pytest.fixture
def config():
    return SimpleNamespace(poll_seconds=0)


def _fixed_primary(monkeypatch):
    monkeypatch.setattr(
        patroni_role_agent,
        "_fetch_configured_patroni_role",
        lambda _config: "primary",
    )


@pytest.mark.parametrize("changed", [False, True])
def test_once_success_emits_one_fixed_receipt(
    config, monkeypatch, capsys, changed
):
    _fixed_primary(monkeypatch)
    monkeypatch.setattr(
        patroni_role_agent,
        "reconcile",
        lambda *_args: changed,
    )

    assert patroni_role_agent.run(config, once=True) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines == ["patroni_role_agent_once_status=verified role=primary"]


def test_once_deferred_returns_temporary_failure_without_receipt(
    config, monkeypatch, capsys
):
    _fixed_primary(monkeypatch)
    monkeypatch.setattr(
        patroni_role_agent,
        "reconcile",
        lambda *_args: None,
    )

    assert patroni_role_agent.run(config, once=True) == 75

    assert "patroni_role_agent_once_status=verified" not in capsys.readouterr().out


def test_once_failure_returns_nonzero_without_receipt(config, monkeypatch, capsys):
    _fixed_primary(monkeypatch)
    monkeypatch.setattr(
        patroni_role_agent,
        "reconcile",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("unsafe runtime")),
    )

    assert patroni_role_agent.run(config, once=True) == 1

    output = capsys.readouterr().out
    assert "patroni_role_agent_status=failed role=primary" in output
    assert "patroni_role_agent_once_status=verified" not in output
