from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = REPO_ROOT / "__init__.py"


class _RegistryStub:
    def get_entry(self, _name):
        return None

    def deregister(self, _name):
        return None


def load_plugin_module():
    tools_module = types.ModuleType("tools")
    registry_module = types.ModuleType("tools.registry")
    registry_module.registry = _RegistryStub()
    registry_module.tool_error = lambda message, **kwargs: {"message": message, **kwargs}
    registry_module.tool_result = lambda payload: payload
    tools_module.registry = registry_module
    sys.modules["tools"] = tools_module
    sys.modules["tools.registry"] = registry_module

    spec = importlib.util.spec_from_file_location("hermes_codex_image_plugin", PLUGIN_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plugin_module():
    return load_plugin_module()


def test_codex_requirement_checks_are_cached(monkeypatch, plugin_module):
    calls = {"count": 0}

    def fake_run(*_args, **_kwargs):
        calls["count"] += 1
        return subprocess.CompletedProcess(
            args=["codex", "features", "list"],
            returncode=0,
            stdout="image_generation stable true\n",
            stderr="",
        )

    monkeypatch.setattr(plugin_module.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(plugin_module.subprocess, "run", fake_run)

    plugin_module._ensure_codex_available()
    plugin_module._ensure_codex_available()

    assert calls["count"] == 1


def test_single_new_output_file_is_renamed_to_expected_name(monkeypatch, plugin_module, tmp_path):
    def fake_run(*_args, **kwargs):
        workdir = Path(kwargs["cwd"])
        (workdir / "variant.png").write_bytes(b"png")
        (workdir / "result.txt").write_text("done", encoding="utf-8")
        return subprocess.CompletedProcess(args=["codex"], returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(plugin_module, "_ensure_codex_available", lambda: None)
    monkeypatch.setattr(plugin_module.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(plugin_module.subprocess, "run", fake_run)

    result = plugin_module.run_codex_image_generation(
        prompt="draw a tangerine",
        file_name="final-image.png",
        output_dir=str(tmp_path),
    )

    assert result["file_name"] == "final-image.png"
    assert Path(result["image_path"]).name == "final-image.png"
    assert not (tmp_path / "variant.png").exists()
    assert (tmp_path / "final-image.png").exists()


def test_multiple_new_output_files_raise_ambiguous_output_error(monkeypatch, plugin_module, tmp_path):
    def fake_run(*_args, **kwargs):
        workdir = Path(kwargs["cwd"])
        (workdir / "option-a.png").write_bytes(b"a")
        (workdir / "option-b.png").write_bytes(b"b")
        return subprocess.CompletedProcess(args=["codex"], returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(plugin_module, "_ensure_codex_available", lambda: None)
    monkeypatch.setattr(plugin_module.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(plugin_module.subprocess, "run", fake_run)

    with pytest.raises(plugin_module.CodexImageGenerationError) as exc:
        plugin_module.run_codex_image_generation(
            prompt="draw a tangerine",
            file_name="final-image.png",
            output_dir=str(tmp_path),
        )

    assert exc.value.code == "AMBIGUOUS_OUTPUT_IMAGE"


def test_success_response_includes_debug_artifact_paths(monkeypatch, plugin_module, tmp_path):
    def fake_run(*_args, **kwargs):
        workdir = Path(kwargs["cwd"])
        (workdir / "final-image.png").write_bytes(b"png")
        (workdir / "result.txt").write_text("last message", encoding="utf-8")
        return subprocess.CompletedProcess(args=["codex"], returncode=0, stdout="stdout text", stderr="stderr text")

    monkeypatch.setattr(plugin_module, "_ensure_codex_available", lambda: None)
    monkeypatch.setattr(plugin_module.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(plugin_module.subprocess, "run", fake_run)

    result = plugin_module.run_codex_image_generation(
        prompt="draw a tangerine",
        file_name="final-image.png",
        output_dir=str(tmp_path),
    )

    assert Path(result["stdout_path"]).read_text(encoding="utf-8") == "stdout text"
    assert Path(result["stderr_path"]).read_text(encoding="utf-8") == "stderr text"
    assert Path(result["result_path"]).read_text(encoding="utf-8") == "last message"


def test_cleanup_stale_temp_dirs_removes_only_old_plugin_directories(plugin_module, tmp_path):
    old_dir = tmp_path / "hermes-codex-imagegen-old"
    recent_dir = tmp_path / "hermes-codex-imagegen-recent"
    other_dir = tmp_path / "keep-me"
    old_dir.mkdir()
    recent_dir.mkdir()
    other_dir.mkdir()

    old_timestamp = 1_700_000_000
    recent_timestamp = old_timestamp + 120
    os.utime(old_dir, (old_timestamp, old_timestamp))
    os.utime(recent_dir, (recent_timestamp, recent_timestamp))

    removed_count = plugin_module._cleanup_stale_temp_dirs(
        base_dir=tmp_path,
        max_age_seconds=60,
        now=recent_timestamp,
        force=True,
    )

    assert removed_count == 1
    assert not old_dir.exists()
    assert recent_dir.exists()
    assert other_dir.exists()
