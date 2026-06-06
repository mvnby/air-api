from io import BytesIO

import pytest
from PIL import Image

from services.product_main_image_cleanup_contract import (
    ProductMainImageCleanupProcessor,
    normalize_cleanup_processor,
)
from services.product_main_image_cleanup_provider import (
    ClassicalTrimMainImageCleanupProcessor,
    ProductMainImageCleanupContext,
    get_main_image_cleanup_processor,
)


def _context() -> ProductMainImageCleanupContext:
    return ProductMainImageCleanupContext(
        product_id=1,
        source_url="/media/products/shared/source.png",
        source_product_image_id=10,
    )


def _image_bytes(image: Image.Image, *, fmt: str = "PNG") -> bytes:
    output = BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


def _opened_size(content: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(content)) as image:
        return image.size


@pytest.mark.asyncio
async def test_classical_trim_crops_transparent_margin_and_preserves_padding():
    image = Image.new("RGBA", (120, 90), (255, 255, 255, 0))
    image.paste((35, 110, 200, 255), box=(30, 25, 90, 65))

    result = await ClassicalTrimMainImageCleanupProcessor().process(
        source_content=_image_bytes(image),
        context=_context(),
    )

    assert result.processor_method == ProductMainImageCleanupProcessor.CLASSICAL_TRIM.value
    assert result.processor_version == "main-cleanup-classical-trim-v1"
    assert result.extension in {"webp", "png"}
    assert result.width is not None
    assert result.height is not None
    assert result.width < 120
    assert result.height < 90
    assert result.width > 60
    assert result.height > 40
    assert _opened_size(result.content) == (result.width, result.height)
    assert result.confidence_score is not None
    assert result.confidence_score >= 0.75
    assert result.quality_score is not None
    assert 0.40 <= result.quality_score <= 1.0


@pytest.mark.asyncio
async def test_classical_trim_crops_white_margin_for_colored_product():
    image = Image.new("RGB", (160, 120), (255, 255, 255))
    image.paste((70, 120, 190), box=(50, 45, 110, 75))

    result = await ClassicalTrimMainImageCleanupProcessor().process(
        source_content=_image_bytes(image),
        context=_context(),
    )

    assert result.width is not None
    assert result.height is not None
    assert result.width < 160
    assert result.height < 120
    assert result.width > 60
    assert result.height > 30
    assert result.confidence_score is not None
    assert result.confidence_score >= 0.75


@pytest.mark.asyncio
async def test_classical_trim_keeps_empty_looking_source_and_lowers_confidence():
    image = Image.new("RGB", (90, 80), (255, 255, 255))

    result = await ClassicalTrimMainImageCleanupProcessor().process(
        source_content=_image_bytes(image),
        context=_context(),
    )

    assert (result.width, result.height) == (90, 80)
    assert _opened_size(result.content) == (90, 80)
    assert result.confidence_score is not None
    assert result.confidence_score <= 0.55
    assert result.quality_score is not None
    assert result.quality_score <= 0.60


def test_processor_factory_keeps_noop_default_and_accepts_classical_trim():
    assert normalize_cleanup_processor(None) == ProductMainImageCleanupProcessor.NOOP.value
    assert get_main_image_cleanup_processor(None).processor_method == "noop"
    assert (
        get_main_image_cleanup_processor("classical_trim").processor_method
        == ProductMainImageCleanupProcessor.CLASSICAL_TRIM.value
    )
