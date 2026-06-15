import sys
from io import BytesIO

import pytest
from PIL import Image

from services.product_image_processing_contract import ProductImageProcessingProvider
from services.product_image_processing_provider import (
    BenProductImageProcessor,
    CommandProductImageProcessor,
    ProductImageProcessingContext,
    RembgProductImageProcessor,
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
