from pathlib import Path

import yaml

from scripts.ha import report_ha_status


REPO_ROOT = Path(__file__).resolve().parents[2]
SSHD_CONFIG = REPO_ROOT / "deploy/ha/security/00-mvn-cicd-reliability.conf"
FAIL2BAN_CONFIG = REPO_ROOT / "deploy/ha/security/mvn-sshd.local"
CHECK_SCRIPT = REPO_ROOT / "scripts/ha/check_host_security.sh"
WORKFLOW = REPO_ROOT / ".github/workflows/check-infrastructure-security.yml"


def test_security_configs_disable_password_login_and_protect_wireguard_clients():
    sshd = SSHD_CONFIG.read_text(encoding="utf-8")
    fail2ban = FAIL2BAN_CONFIG.read_text(encoding="utf-8")

    assert "PasswordAuthentication no" in sshd
    assert "KbdInteractiveAuthentication no" in sshd
    assert "PermitRootLogin prohibit-password" in sshd
    assert "MaxStartups 20:30:40" in sshd
    assert "PerSourceMaxStartups 10" in sshd
    assert "backend = systemd" in fail2ban
    assert "ignoreip = 127.0.0.1/8 ::1 10.77.0.0/29" in fail2ban


def test_host_checker_covers_effective_config_and_private_listener_ownership():
    script = CHECK_SCRIPT.read_text(encoding="utf-8")

    assert "sshd" in script and "-T" in script
    assert "fail2ban-client get" in script
    assert "wg show wg-mvn" in script
    assert "SENSITIVE_TCP_PORTS" in script
    assert "sensitive listener" in script
    assert "status=passed failures=0" in script


def test_security_workflow_checks_three_hosts_and_alerts():
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["check"]
    steps = {step["name"]: step for step in job["steps"]}

    assert workflow["on"]["schedule"][0]["cron"] == "37 */6 * * *"
    audit = steps["Audit host hardening and private listeners"]["run"]
    assert "labels=(mvn-api zakup mvn-web)" in audit
    assert "scripts/ha/check_host_security.sh" in audit
    assert "API_DB_HA_MODE" in audit
    audit_env = steps["Audit host hardening and private listeners"]["env"]
    assert "INFRA_SECURITY_WEB_USER" in audit_env["WEB_USER"]
    public_scan = steps["Verify sensitive ports are closed publicly"]["run"]
    assert "2379 2380 5432 8008 18000 18001 18002 18080" in public_scan
    assert steps["Upload security audit log"]["if"] == "always()"
    assert steps["Notify HA failure"]["if"] == "failure()"


def test_security_workflow_is_part_of_the_strict_ha_rollup():
    expected = {workflow.name: workflow for workflow in report_ha_status.EXPECTED_WORKFLOWS}

    assert expected["Infrastructure Security Check"].max_age_hours == 8
