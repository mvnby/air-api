import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts/check_media_storage_config.py"
SPEC = importlib.util.spec_from_file_location("check_media_storage_config", MODULE_PATH)
media_check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = media_check
SPEC.loader.exec_module(media_check)


def _set_r2_env(monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
    monkeypatch.setenv("PRODUCT_MEDIA_STORAGE_PROVIDER", "r2")
    monkeypatch.setenv("PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER", "r2")
    monkeypatch.setenv("PRODUCT_MEDIA_S3_BUCKET", "mvn-media")
    monkeypatch.setenv(
        "PRODUCT_MEDIA_S3_ENDPOINT_URL",
        "https://example-account.r2.cloudflarestorage.com",
    )
    monkeypatch.setenv("PRODUCT_MEDIA_S3_PUBLIC_BASE_URL", "https://cdn.mvn.by")
    monkeypatch.setenv("PRODUCT_MEDIA_S3_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("PRODUCT_MEDIA_S3_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("PRODUCT_MEDIA_S3_KEY_PREFIX", "products/variants")
    monkeypatch.delenv("MEDIA_S3_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("MEDIA_S3_KEY_PREFIX", raising=False)


def test_media_storage_config_passes_when_all_runtime_media_targets_r2(monkeypatch, capsys):
    _set_r2_env(monkeypatch)

    exit_code = media_check.main(
        ["--require-object-storage", "--expected-public-base-url", "https://cdn.mvn.by"]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "label=general_media provider=r2 url=https://cdn.mvn.by/orders/121/telegram/photo/" in output
    assert "label=product_variants provider=r2 url=https://cdn.mvn.by/products/variants/original/" in output
    assert "label=product_originals provider=r2 url=https://cdn.mvn.by/products/shared/" in output
    assert "media_storage_config_status=passed" in output


def test_media_storage_config_fails_when_product_originals_remain_local(monkeypatch, capsys):
    _set_r2_env(monkeypatch)
    monkeypatch.delenv("PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER", raising=False)

    exit_code = media_check.main(
        ["--require-object-storage", "--expected-public-base-url", "https://cdn.mvn.by"]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "label=product_originals provider=local url=/media/products/shared/" in captured.out
    assert "product_originals provider is 'local'" in captured.err


def test_media_storage_config_allows_local_defaults_without_strict_requirement(monkeypatch):
    for key in [
        "MEDIA_STORAGE_PROVIDER",
        "PRODUCT_MEDIA_STORAGE_PROVIDER",
        "PRODUCT_MEDIA_ORIGINAL_SOURCE_PROVIDER",
        "MEDIA_S3_PUBLIC_BASE_URL",
        "PRODUCT_MEDIA_S3_PUBLIC_BASE_URL",
    ]:
        monkeypatch.delenv(key, raising=False)

    exit_code = media_check.main([])

    assert exit_code == 0
