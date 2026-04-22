from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "install.sh"


def _make_raw_base(tmp_path: Path) -> Path:
    raw_base = tmp_path / "raw"
    raw_base.mkdir()
    (raw_base / "plugin.yaml").write_text("name: codex_image_gen\n", encoding="utf-8")
    (raw_base / "__init__.py").write_text("PLUGIN = True\n", encoding="utf-8")
    return raw_base


def _run_install(tmp_path: Path, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(extra_env)
    return subprocess.run(
        ["bash", str(INSTALL_SCRIPT)],
        cwd=str(REPO_ROOT),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_install_script_installs_into_root_and_all_profiles_by_default(tmp_path: Path):
    raw_base = _make_raw_base(tmp_path)
    hermes_root = tmp_path / ".hermes"
    current_profile = hermes_root / "profiles" / "alpha"
    other_profile = hermes_root / "profiles" / "beta"
    current_profile.mkdir(parents=True)
    other_profile.mkdir(parents=True)

    result = _run_install(
        tmp_path,
        {
            "HOME": str(tmp_path),
            "HERMES_HOME": str(current_profile),
            "HERMES_GPT_IMAGE_GEN_RAW_BASE": raw_base.as_uri(),
        },
    )

    assert result.returncode == 0, result.stderr
    assert (hermes_root / "plugins" / "codex_image_gen" / "plugin.yaml").exists()
    assert (current_profile / "plugins" / "codex_image_gen" / "plugin.yaml").exists()
    assert (other_profile / "plugins" / "codex_image_gen" / "plugin.yaml").exists()


def test_install_script_respects_explicit_destination_override(tmp_path: Path):
    raw_base = _make_raw_base(tmp_path)
    hermes_root = tmp_path / ".hermes"
    profile = hermes_root / "profiles" / "alpha"
    profile.mkdir(parents=True)
    explicit_dest = tmp_path / "custom-plugin-dir"

    result = _run_install(
        tmp_path,
        {
            "HOME": str(tmp_path),
            "HERMES_HOME": str(profile),
            "HERMES_GPT_IMAGE_GEN_RAW_BASE": raw_base.as_uri(),
            "HERMES_GPT_IMAGE_GEN_DIR": str(explicit_dest),
        },
    )

    assert result.returncode == 0, result.stderr
    assert (explicit_dest / "plugin.yaml").exists()
    assert not (hermes_root / "plugins" / "codex_image_gen").exists()
    assert not (profile / "plugins" / "codex_image_gen").exists()
