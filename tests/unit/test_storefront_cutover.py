from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_api_repository_keeps_storefront_as_an_external_service():
    """Prevent an accidental return to an embedded storefront publisher."""
    legacy_web = ROOT / "web"
    allowed_runtime_roots = (
        legacy_web / "node_modules",
        legacy_web / "public" / "media",
    )
    embedded_storefront_files = (
        []
        if not legacy_web.exists()
        else [
            path.relative_to(ROOT)
            for path in legacy_web.rglob("*")
            if (path.is_file() or path.is_symlink())
            and not any(path.is_relative_to(root) for root in allowed_runtime_roots)
        ]
    )
    assert embedded_storefront_files == []
    assert not (ROOT / "docker-compose.web.yml").exists()
    assert not (ROOT / ".github/workflows/deploy-web.yml").exists()
    assert not (ROOT / ".github/workflows/rebuild-web.yml").exists()

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "\n  web:\n" not in compose

    config = (ROOT / "core/config.py").read_text(encoding="utf-8")
    service = (ROOT / "services/system_service.py").read_text(encoding="utf-8")
    assert 'WEB_REBUILD_GITHUB_REPO: str = "mvn-web"' in config
    assert 'workflow_id = "rebuild-web.yml"' in service
