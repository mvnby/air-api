import json
from pathlib import Path

import pytest

from scripts.ha import recover_patroni_preflight_incident as orchestrator
from scripts.ha.pitr_cluster_topology import ClusterTopology
from scripts.ha.pitr_pinned_ssh import PATRONI_NODES


MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "deploy/ha/patroni/incidents/1053e46eb933ebaaffed042ac1b73170.json"
)
DEPLOY_SHA = "a" * 40


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="ascii"))


def _topology():
    nodes = {node.alias: node for node in PATRONI_NODES}
    baseline = _manifest()["baseline"]
    return ClusterTopology(
        primary=nodes["mvn-api"],
        standby=nodes["zakup"],
        system_identifier=str(baseline["system_identifier"]),
        timeline=int(baseline["timeline"]),
    )


class StableDiscovery:
    def __init__(self, *, fail_once_at=None):
        self.calls = 0
        self.fail_once_at = fail_once_at
        self.failed = False

    def __call__(self, **_kwargs):
        self.calls += 1
        if self.calls == self.fail_once_at and not self.failed:
            self.failed = True
            raise RuntimeError("simulated topology crash window")
        return _topology()


class RecoveryRemote:
    def __init__(self, *, fail_once=None, initial=None):
        self.calls = []
        self.fail_once = fail_once
        self.failed = False
        self.state = {
            node.alias: {
                "journal_state": "before",
                "marker_present": True,
                "receipt_present": False,
            }
            for node in PATRONI_NODES
        }
        for alias, values in (initial or {}).items():
            self.state[alias].update(values)

    def __call__(self, *, action, node, **_kwargs):
        key = (action, node.alias)
        self.calls.append(key)
        if key == self.fail_once and not self.failed:
            self.failed = True
            raise RuntimeError("simulated remote crash window")
        state = self.state[node.alias]
        if action == "terminalize":
            state["journal_state"] = "after"
            state["receipt_present"] = True
        elif action == "unfence":
            state["marker_present"] = False
        return {"node": node.alias, **state}


def _prepare(monkeypatch):
    manifest = _manifest()
    expected_contracts = {
        alias: values["compose_contract_sha256"]
        for alias, values in manifest["nodes"].items()
    }
    monkeypatch.setattr(orchestrator, "_safe_manifest", lambda _path: manifest)
    monkeypatch.setattr(
        orchestrator,
        "local_contract_digests",
        lambda _deploy_sha: expected_contracts,
    )
    return manifest


def _recover(monkeypatch, remote, discover):
    _prepare(monkeypatch)
    return orchestrator.recover_patroni_preflight_incident(
        context=object(),
        recovery_deploy_sha=DEPLOY_SHA,
        manifest_path=MANIFEST_PATH,
        runner=lambda *_args, **_kwargs: pytest.fail("runner must stay behind fakes"),
        discover=discover,
        remote=remote,
    )


def test_resume_after_only_standby_was_terminalized(monkeypatch):
    remote = RecoveryRemote(fail_once=("terminalize", "mvn-api"))
    discover = StableDiscovery()

    with pytest.raises(RuntimeError, match="remote crash window"):
        _recover(monkeypatch, remote, discover)
    assert remote.state["zakup"]["journal_state"] == "after"
    assert remote.state["mvn-api"]["journal_state"] == "before"

    checkpoint = len(remote.calls)
    result = _recover(monkeypatch, remote, discover)
    resumed = remote.calls[checkpoint:]

    assert ("terminalize", "zakup") not in resumed
    assert resumed.count(("terminalize", "mvn-api")) == 1
    assert result.primary == "mvn-api"
    assert all(not state["marker_present"] for state in remote.state.values())


def test_resume_after_both_journals_terminalized_before_topology_reproof(monkeypatch):
    remote = RecoveryRemote()
    discover = StableDiscovery(fail_once_at=2)

    with pytest.raises(RuntimeError, match="topology crash window"):
        _recover(monkeypatch, remote, discover)
    assert all(state["journal_state"] == "after" for state in remote.state.values())
    assert all(state["receipt_present"] for state in remote.state.values())

    checkpoint = len(remote.calls)
    _recover(monkeypatch, remote, discover)
    resumed = remote.calls[checkpoint:]

    assert all(action != "terminalize" for action, _alias in resumed)
    assert all(not state["marker_present"] for state in remote.state.values())


def test_resume_after_only_standby_was_unfenced(monkeypatch):
    remote = RecoveryRemote(fail_once=("unfence", "mvn-api"))
    discover = StableDiscovery()

    with pytest.raises(RuntimeError, match="remote crash window"):
        _recover(monkeypatch, remote, discover)
    assert remote.state["zakup"]["marker_present"] is False
    assert remote.state["mvn-api"]["marker_present"] is True
    assert all(state["journal_state"] == "after" for state in remote.state.values())

    checkpoint = len(remote.calls)
    _recover(monkeypatch, remote, discover)
    resumed = remote.calls[checkpoint:]

    assert all(action != "terminalize" for action, _alias in resumed)
    assert resumed.count(("unfence", "zakup")) == 1
    assert resumed.count(("unfence", "mvn-api")) == 1
    assert all(not state["marker_present"] for state in remote.state.values())


def test_rejects_partial_unfence_without_two_terminal_receipts(monkeypatch):
    remote = RecoveryRemote(
        initial={
            "zakup": {
                "journal_state": "after",
                "marker_present": False,
                "receipt_present": True,
            }
        }
    )

    with pytest.raises(RuntimeError, match="partial unfence exists"):
        _recover(monkeypatch, remote, StableDiscovery())

    assert remote.calls == [("probe", "mvn-api"), ("probe", "zakup")]
