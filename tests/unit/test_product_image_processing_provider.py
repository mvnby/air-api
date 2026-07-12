import subprocess
import sys
import time
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
    _background_removal_rembg_process_mode,
    _background_removal_rembg_model,
    _background_removal_timeout_seconds,
    _get_rembg_session,
    _render_command_argv,
    _run_rembg_subprocess,
    _should_run_rembg_in_subprocess,
    background_removal_provider_options,
    get_product_image_processor,
    rembg_model_options,
    rembg_preload_model_names,
    resolve_background_removal_provider,
    warmup_rembg_models,
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


def test_rembg_model_options_expose_only_safe_default_candidates():
    values = [item["value"] for item in rembg_model_options()]

    assert values == ["u2net"]


def test_rembg_model_options_keep_experimental_candidates_for_manual_ops():
    values = {item["value"] for item in rembg_model_options(include_experimental=True)}

    assert {
        "u2net",
        "isnet-general-use",
        "birefnet-general-lite",
        "birefnet-general",
        "birefnet-massive",
        "bria-rmbg",
    } <= values


def test_rembg_preload_models_use_default_and_env_override(monkeypatch):
    monkeypatch.delenv("BACKGROUND_REMOVAL_REMBG_PRELOAD_MODELS", raising=False)
    assert rembg_preload_model_names() == ["u2net"]

    monkeypatch.setenv("BACKGROUND_REMOVAL_REMBG_PRELOAD_MODELS", "u2net, birefnet-general, u2net")
    assert rembg_preload_model_names() == ["u2net", "birefnet-general"]


def test_rembg_preload_models_reject_unknown_model(monkeypatch):
    monkeypatch.setenv("BACKGROUND_REMOVAL_REMBG_PRELOAD_MODELS", "u2net,unknown")

    with pytest.raises(ValueError, match="Unsupported rembg preload model"):
        rembg_preload_model_names()


def test_warmup_rembg_models_creates_sessions(monkeypatch):
    created = []

    class FakeRembgModule:
        @staticmethod
        def new_session(model_name):
            created.append(model_name)
            return {"model": model_name}

    monkeypatch.setitem(sys.modules, "rembg", FakeRembgModule)
    _get_rembg_session.cache_clear()

    results = warmup_rembg_models(["u2net", "birefnet-general"])

    assert results == [
        {"model": "u2net", "status": "ready"},
        {"model": "birefnet-general", "status": "ready"},
    ]
    assert created == ["u2net", "birefnet-general"]


def test_background_removal_timeout_uses_safe_default_and_env(monkeypatch):
    monkeypatch.delenv("BACKGROUND_REMOVAL_TIMEOUT_SECONDS", raising=False)
    assert _background_removal_timeout_seconds() == DEFAULT_BACKGROUND_REMOVAL_TIMEOUT_SECONDS

    monkeypatch.setenv("BACKGROUND_REMOVAL_TIMEOUT_SECONDS", "180")
    assert _background_removal_timeout_seconds() == 180

    monkeypatch.setenv("BACKGROUND_REMOVAL_TIMEOUT_SECONDS", "invalid")
    assert _background_removal_timeout_seconds() == DEFAULT_BACKGROUND_REMOVAL_TIMEOUT_SECONDS


def test_command_template_is_rendered_as_argv_without_shell_interpolation():
    command = _render_command_argv(
        "processor --input {input} --output={output} '; touch /tmp/owned'",
        input_path="/tmp/source image.png",
        output_path="/tmp/result image.png",
    )

    assert command == [
        "processor",
        "--input",
        "/tmp/source image.png",
        "--output=/tmp/result image.png",
        "; touch /tmp/owned",
    ]


def test_command_template_requires_both_file_placeholders():
    with pytest.raises(RuntimeError, match="must contain"):
        _render_command_argv(
            "processor --input {input}",
            input_path="/tmp/source.png",
            output_path="/tmp/result.png",
        )


def test_rembg_process_mode_uses_experimental_default_and_env(monkeypatch):
    monkeypatch.delenv("BACKGROUND_REMOVAL_REMBG_PROCESS_MODE", raising=False)
    assert _background_removal_rembg_process_mode() == "experimental"

    monkeypatch.setenv("BACKGROUND_REMOVAL_REMBG_PROCESS_MODE", "always")
    assert _background_removal_rembg_process_mode() == "always"

    monkeypatch.setenv("BACKGROUND_REMOVAL_REMBG_PROCESS_MODE", "invalid")
    assert _background_removal_rembg_process_mode() == "experimental"


def test_rembg_process_mode_isolates_experimental_models(monkeypatch):
    monkeypatch.setenv("BACKGROUND_REMOVAL_REMBG_PROCESS_MODE", "experimental")
    assert _should_run_rembg_in_subprocess("u2net") is False
    assert _should_run_rembg_in_subprocess("birefnet-general") is True

    monkeypatch.setenv("BACKGROUND_REMOVAL_REMBG_PROCESS_MODE", "always")
    assert _should_run_rembg_in_subprocess("u2net") is True

    monkeypatch.setenv("BACKGROUND_REMOVAL_REMBG_PROCESS_MODE", "never")
    assert _should_run_rembg_in_subprocess("birefnet-general") is False


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
    monkeypatch.setenv("BACKGROUND_REMOVAL_REMBG_PROCESS_MODE", "never")
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
async def test_rembg_processor_times_out_without_blocking_event_loop(monkeypatch):
    class FakeRembgModule:
        @staticmethod
        def new_session(model_name):
            return {"model": model_name}

        @staticmethod
        def remove(source_content, *, session):
            time.sleep(0.05)
            return source_content

    monkeypatch.setitem(sys.modules, "rembg", FakeRembgModule)
    monkeypatch.setattr(
        "services.product_image_processing_provider._background_removal_timeout_seconds",
        lambda: 0.01,
    )
    _get_rembg_session.cache_clear()

    processor = RembgProductImageProcessor(model_name="u2net")

    with pytest.raises(RuntimeError, match="rembg provider timed out"):
        await processor.process(
            source_content=image_bytes(size=(40, 30)),
            context=ProductImageProcessingContext(
                product_image_id=1,
                source_url="/media/source.png",
                variant_type="processed",
            ),
        )


@pytest.mark.asyncio
async def test_rembg_processor_uses_subprocess_for_experimental_model(monkeypatch):
    calls = []

    def fake_run_rembg_subprocess(*, model_name, source_content, timeout_seconds):
        calls.append((model_name, source_content, timeout_seconds))
        return source_content

    monkeypatch.setenv("BACKGROUND_REMOVAL_REMBG_PROCESS_MODE", "experimental")
    monkeypatch.setenv("BACKGROUND_REMOVAL_TIMEOUT_SECONDS", "7")
    monkeypatch.setattr(
        "services.product_image_processing_provider._run_rembg_subprocess",
        fake_run_rembg_subprocess,
    )

    processor = RembgProductImageProcessor(model_name="birefnet-general")
    source_content = image_bytes(size=(40, 30))
    result = await processor.process(
        source_content=source_content,
        context=ProductImageProcessingContext(
            product_image_id=1,
            source_url="/media/source.png",
            variant_type="processed",
        ),
    )

    assert result.width == 40
    assert calls == [("birefnet-general", source_content, 7)]


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
    monkeypatch.setenv("BACKGROUND_REMOVAL_REMBG_PROCESS_MODE", "never")
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


def test_rembg_subprocess_reads_output(tmp_path, monkeypatch):
    source_content = image_bytes(size=(40, 30))

    def fake_run(command, *, check, capture_output, text, timeout):
        output_path = command[command.index("--output") + 1]
        with open(output_path, "wb") as output_file:
            output_file.write(source_content)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    output = _run_rembg_subprocess(
        model_name="birefnet-general",
        source_content=source_content,
        timeout_seconds=5,
    )

    assert output == source_content


def test_rembg_subprocess_wraps_timeout(monkeypatch):
    def fake_run(command, *, check, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="rembg subprocess timed out"):
        _run_rembg_subprocess(
            model_name="birefnet-general",
            source_content=image_bytes(size=(40, 30)),
            timeout_seconds=5,
        )


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


@pytest.mark.asyncio
async def test_command_provider_wraps_timeout(tmp_path, monkeypatch):
    script = tmp_path / "slow_image.py"
    script.write_text("import time\n" "time.sleep(3)\n")
    processor = CommandProductImageProcessor(
        provider_name="birefnet",
        command_env="TEST_SLOW_BIREFNET_COMMAND",
        timeout_seconds=1,
    )

    monkeypatch.setenv(
        "TEST_SLOW_BIREFNET_COMMAND",
        f"{sys.executable} {script} {{input}} {{output}}",
    )

    with pytest.raises(RuntimeError, match="provider timed out"):
        await processor.process(
            source_content=image_bytes(size=(40, 30)),
            context=ProductImageProcessingContext(
                product_image_id=1,
                source_url="/media/source.png",
                variant_type="processed",
            ),
        )
