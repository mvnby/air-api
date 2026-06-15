import sys
from io import BytesIO

import pytest
from PIL import Image

from services.product_image_processing_contract import ProductImageProcessingProvider
from services.product_image_processing_provider import (
    BenProductImageProcessor,
    CommandProductImageProcessor,
    DEFAULT_BACKGROUND_REMOVAL_REMBG_MODEL,
    DEFAULT_BACKGROUND_REMOVAL_TIMEOUT_SECONDS,
    ProductImageProcessingContext,
    RembgProductImageProcessor,
    _background_removal_rembg_model,
    _background_removal_timeout_seconds,
    _get_rembg_session,
    background_removal_provider_options,
    get_product_image_processor,
    resolve_background_removal_provider,
)


def image_bytes(size=(120, 80), color=(20, 180, 160)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_auto_provider_uses_default_when_env_is_empty(monkeypatch):
    monkeypatch.delenv("BACKGROUND_REMOVAL_PROVIDER", raising=False)

    assert resolve_background_removal_provider("auto") == ProductImageProcessingProvider.REMBG.value
    assert isinstance(get_product_image_processor("auto"), RembgProductImageProcessor)


def test_auto_provider_uses_env_override(monkeypatch):
    monkeypatch.setenv("BACKGROUND_REMOVAL_PROVIDER", "ben")

    processor = get_product_image_processor("auto")

    assert isinstance(processor, BenProductImageProcessor)
    assert processor.provider_name == "ben"


def test_background_provider_options_include_candidate_models():
    values = {item["value"] for item in background_removal_provider_options()}

    assert {"auto", "rembg", "birefnet", "ben", "noop", "manual"} <= values


def test_rembg_model_uses_default_and_env_override(monkeypatch):
    monkeypatch.delenv("BACKGROUND_REMOVAL_REMBG_MODEL", raising=False)
    assert _background_removal_rembg_model() == DEFAULT_BACKGROUND_REMOVAL_REMBG_MODEL

    monkeypatch.setenv("BACKGROUND_REMOVAL_REMBG_MODEL", "isnet-general-use")
    assert _background_removal_rembg_model() == "isnet-general-use"


def test_rembg_processor_records_model_in_provider_name():
    processor = get_product_image_processor("rembg", rembg_model="isnet-general-use")

    assert isinstance(processor, RembgProductImageProcessor)
    assert processor.provider_name == "rembg:isnet-general-use"


def test_background_removal_timeout_uses_safe_default_and_env(monkeypatch):
    monkeypatch.delenv("BACKGROUND_REMOVAL_TIMEOUT_SECONDS", raising=False)
    assert _background_removal_timeout_seconds() == DEFAULT_BACKGROUND_REMOVAL_TIMEOUT_SECONDS

    monkeypatch.setenv("BACKGROUND_REMOVAL_TIMEOUT_SECONDS", "180")
    assert _background_removal_timeout_seconds() == 180

    monkeypatch.setenv("BACKGROUND_REMOVAL_TIMEOUT_SECONDS", "invalid")
    assert _background_removal_timeout_seconds() == DEFAULT_BACKGROUND_REMOVAL_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_rembg_processor_passes_configured_session(monkeypatch):
    sessions = []
    removed_sessions = []

    class FakeRembgModule:
        @staticmethod
        def new_session(model_name):
            session = {"model": model_name}
            sessions.append(session)
            return session

        @staticmethod
        def remove(source_content, *, session):
            removed_sessions.append(session)
            return source_content

    monkeypatch.setitem(sys.modules, "rembg", FakeRembgModule)
    _get_rembg_session.cache_clear()

    processor = RembgProductImageProcessor(model_name="isnet-general-use")
    result = await processor.process(
        source_content=image_bytes(size=(40, 30)),
        context=ProductImageProcessingContext(
            product_image_id=1,
            source_url="/media/source.png",
            variant_type="processed",
        ),
    )

    assert result.width == 40
    assert sessions == [{"model": "isnet-general-use"}]
    assert removed_sessions == [{"model": "isnet-general-use"}]


@pytest.mark.asyncio
async def test_rembg_session_is_cached_per_model(monkeypatch):
    created = []

    class FakeRembgModule:
        @staticmethod
        def new_session(model_name):
            created.append(model_name)
            return {"model": model_name, "index": len(created)}

        @staticmethod
        def remove(source_content, *, session):
            return source_content

    monkeypatch.setitem(sys.modules, "rembg", FakeRembgModule)
    _get_rembg_session.cache_clear()
    processor = RembgProductImageProcessor(model_name="u2netp")

    for _ in range(2):
        await processor.process(
            source_content=image_bytes(size=(40, 30)),
            context=ProductImageProcessingContext(
                product_image_id=1,
                source_url="/media/source.png",
                variant_type="processed",
            ),
        )

    assert created == ["u2netp"]


def test_rembg_session_wraps_invalid_model_errors(monkeypatch):
    class FakeRembgModule:
        @staticmethod
        def new_session(model_name):
            raise ValueError("bad model")

    monkeypatch.setitem(sys.modules, "rembg", FakeRembgModule)
    _get_rembg_session.cache_clear()

    with pytest.raises(RuntimeError, match="rembg model is not configured correctly"):
        _get_rembg_session("bad-model")


@pytest.mark.asyncio
async def test_command_provider_runs_configured_adapter(tmp_path, monkeypatch):
    script = tmp_path / "copy_image.py"
    script.write_text(
        "import shutil, sys\n"
        "shutil.copyfile(sys.argv[1], sys.argv[2])\n"
    )
    processor = CommandProductImageProcessor(
        provider_name="ben",
        command_env="TEST_BEN_COMMAND",
        timeout_seconds=5,
    )

    monkeypatch.setenv("TEST_BEN_COMMAND", f"{sys.executable} {script} {{input}} {{output}}")
    result = await processor.process(
        source_content=image_bytes(size=(40, 30)),
        context=ProductImageProcessingContext(
            product_image_id=1,
            source_url="/media/source.png",
            variant_type="processed",
        ),
    )

    assert result.content
    assert result.width == 40
    assert result.height == 30


@pytest.mark.asyncio
async def test_command_provider_requires_command_env():
    processor = CommandProductImageProcessor(
        provider_name="birefnet",
        command_env="TEST_MISSING_BIREFNET_COMMAND",
        timeout_seconds=5,
    )

    with pytest.raises(RuntimeError, match="not configured"):
        await processor.process(
            source_content=image_bytes(size=(40, 30)),
            context=ProductImageProcessingContext(
                product_image_id=1,
                source_url="/media/source.png",
                variant_type="processed",
            ),
        )
