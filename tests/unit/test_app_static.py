from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.app_static import mount_static_and_media


def test_media_static_files_serve_webp_with_image_content_type(tmp_path: Path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "sample.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBP")

    app = FastAPI()
    mount_static_and_media(app, tmp_path)

    response = TestClient(app).get("/media/sample.webp")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/webp")
