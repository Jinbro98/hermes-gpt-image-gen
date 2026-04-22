from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from tools.registry import registry, tool_error, tool_result

VALID_ASPECT_RATIOS = ("landscape", "square", "portrait")
VALID_BACKGROUNDS = ("auto", "transparent", "opaque")
IMAGE_EXTENSIONS = (".png", ".webp", ".jpg", ".jpeg")
TRIGGER_ENGINE_TERMS = ("덕테이프로", "코덱스로", "gpt로")
TRIGGER_IMAGE_TERMS = ("이미지", "그림", "아이콘", "일러스트")
TRIGGER_ACTION_TERMS = ("생성", "만들", "그려", "제작", "렌더")
DEFAULT_TIMEOUT_SECONDS = 600
MAX_LOG_TEXT_CHARS = 1200
OVERRIDE_ENV_VAR = "HERMES_CODEX_IMAGEGEN_OVERRIDE"
TEMP_DIR_PREFIX = "hermes-codex-imagegen-"
REQUIREMENTS_CACHE_TTL_SECONDS = int(os.getenv("HERMES_CODEX_IMAGEGEN_REQUIREMENTS_TTL", "300"))
TEMP_DIR_MAX_AGE_SECONDS = int(os.getenv("HERMES_CODEX_IMAGEGEN_TEMP_DIR_MAX_AGE", "86400"))
TEMP_DIR_CLEANUP_INTERVAL_SECONDS = int(
    os.getenv("HERMES_CODEX_IMAGEGEN_CLEANUP_INTERVAL", "3600")
)

_CODEX_REQUIREMENTS_CACHE = {
    "checked_at": 0.0,
    "ok": None,
    "error": None,
    "codex_bin": None,
}
_LAST_TEMP_DIR_CLEANUP_AT = 0.0


class CodexImageGenerationError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        debug_paths: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.debug_paths = debug_paths or {}


CODEX_IMAGE_GENERATE_SCHEMA = {
    "name": "codex_image_generate",
    "description": (
        "Generate an image via Codex CLI and return a local file path. "
        "Best for workflows that need a saved image file which can then be sent as media, "
        "for example with MEDIA:/absolute/path in Telegram."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The image prompt to render.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": list(VALID_ASPECT_RATIOS),
                "description": "Requested framing: landscape (16:9), square (1:1), or portrait (9:16).",
                "default": "landscape",
            },
            "file_name": {
                "type": "string",
                "description": "Optional output file name. Defaults to a sanitized PNG filename.",
            },
            "output_dir": {
                "type": "string",
                "description": "Optional output directory. Defaults to a fresh temporary directory.",
            },
            "background": {
                "type": "string",
                "enum": list(VALID_BACKGROUNDS),
                "description": "Background preference: auto, transparent, or opaque.",
                "default": "auto",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Max time to wait for Codex CLI image generation.",
                "default": DEFAULT_TIMEOUT_SECONDS,
            },
        },
        "required": ["prompt"],
    },
}

OVERRIDE_IMAGE_GENERATE_SCHEMA = {
    **CODEX_IMAGE_GENERATE_SCHEMA,
    "name": "image_generate",
    "description": (
        "Generate an image via Codex CLI and return a local file path instead of a URL. "
        "Use MEDIA:/absolute/path to send the generated image directly in Telegram."
    ),
}


def _aspect_ratio_instruction(aspect_ratio: str) -> str:
    mapping = {
        "landscape": "Target aspect ratio: landscape / 16:9.",
        "square": "Target aspect ratio: square / 1:1.",
        "portrait": "Target aspect ratio: portrait / 9:16.",
    }
    return mapping[aspect_ratio]



def _background_instruction(background: str) -> str:
    mapping = {
        "auto": "Choose the most appropriate background for the concept.",
        "transparent": "Use a transparent background if the model supports it; otherwise keep the background visually minimal.",
        "opaque": "Use an opaque, fully rendered background.",
    }
    return mapping[background]



def _safe_file_name(file_name: Optional[str]) -> str:
    raw_name = Path(file_name or "codex-image.png").name
    stem = Path(raw_name).stem
    suffix = Path(raw_name).suffix.lower()
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("._-") or "codex-image"
    if suffix not in IMAGE_EXTENSIONS:
        suffix = ".png"
    return f"{safe_stem}{suffix}"



def _build_codex_prompt(prompt: str, aspect_ratio: str, file_name: str, background: str) -> str:
    return (
        "$imagegen\n"
        "Create exactly one final image that satisfies the request below.\n\n"
        f"Creative brief:\n{prompt.strip()}\n\n"
        "Output requirements:\n"
        f"- Save the final image in the current working directory as \"{file_name}\".\n"
        "- Use PNG format for the final saved file.\n"
        f"- {_aspect_ratio_instruction(aspect_ratio)}\n"
        f"- {_background_instruction(background)}\n"
        "- Do not return markdown or code fences.\n"
        "- If you explore variants, still finish by saving exactly one final image with the requested filename.\n"
    )



def _collect_image_files(workdir: Path) -> list[Path]:
    return [
        path
        for path in workdir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]



def _snapshot_image_files(workdir: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in _collect_image_files(workdir):
        stat = path.stat()
        snapshot[path.name] = (stat.st_mtime_ns, stat.st_size)
    return snapshot



def _is_new_or_changed(path: Path, snapshot: dict[str, tuple[int, int]]) -> bool:
    stat = path.stat()
    return snapshot.get(path.name) != (stat.st_mtime_ns, stat.st_size)



def _write_debug_artifacts(workdir: Path, stdout_text: str, stderr_text: str) -> dict[str, str]:
    stdout_path = workdir / "codex.stdout.log"
    stderr_path = workdir / "codex.stderr.log"
    stdout_path.write_text(stdout_text or "", encoding="utf-8")
    stderr_path.write_text(stderr_text or "", encoding="utf-8")
    return {
        "stdout_path": str(stdout_path.resolve()),
        "stderr_path": str(stderr_path.resolve()),
        "result_path": str((workdir / "result.txt").resolve()),
    }



def _resolve_generated_file(
    workdir: Path,
    expected_name: str,
    snapshot: dict[str, tuple[int, int]],
) -> Path:
    expected_path = workdir / expected_name
    if expected_path.exists() and _is_new_or_changed(expected_path, snapshot):
        return expected_path

    candidates = [path for path in _collect_image_files(workdir) if _is_new_or_changed(path, snapshot)]
    if not candidates:
        raise CodexImageGenerationError(
            "IMAGE_NOT_PRODUCED",
            f"Codex CLI finished without leaving a new image file in {workdir}",
        )
    if len(candidates) > 1:
        candidate_names = ", ".join(sorted(path.name for path in candidates))
        raise CodexImageGenerationError(
            "AMBIGUOUS_OUTPUT_IMAGE",
            (
                "Codex CLI produced multiple new image files without the expected filename: "
                f"{candidate_names}"
            ),
        )

    candidate = candidates[0]
    if candidate.name != expected_name and candidate.suffix.lower() == expected_path.suffix.lower():
        candidate.replace(expected_path)
        return expected_path
    return candidate



def _truncate_log_text(text: str, limit: int = MAX_LOG_TEXT_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}… [truncated]"



def _looks_like_image_request(message: str) -> bool:
    return (
        any(term in message for term in TRIGGER_IMAGE_TERMS)
        and any(term in message for term in TRIGGER_ACTION_TERMS)
    )



def _build_routing_context(user_message: str | None):
    normalized = (user_message or "").strip().casefold()
    if not normalized or not _looks_like_image_request(normalized):
        return None
    if not any(term in normalized for term in TRIGGER_ENGINE_TERMS):
        return None
    if not check_codex_imagegen_requirements():
        return None

    return {
        "context": (
            "Routing hint: the user explicitly requested Codex/GPT-style image generation. "
            "Use `codex_image_generate` for the image generation step unless the user explicitly asks for another backend."
        )
    }



def _ensure_codex_available(force_refresh: bool = False) -> str:
    now = time.monotonic()
    cached_ok = _CODEX_REQUIREMENTS_CACHE["ok"]
    checked_at = _CODEX_REQUIREMENTS_CACHE["checked_at"]
    if (
        not force_refresh
        and cached_ok is not None
        and now - checked_at < REQUIREMENTS_CACHE_TTL_SECONDS
    ):
        if cached_ok:
            return str(_CODEX_REQUIREMENTS_CACHE["codex_bin"])
        raise RuntimeError(str(_CODEX_REQUIREMENTS_CACHE["error"]))

    codex_bin = shutil.which("codex")
    if not codex_bin:
        error = "Codex CLI not found in PATH."
        _CODEX_REQUIREMENTS_CACHE.update(
            {"checked_at": now, "ok": False, "error": error, "codex_bin": None}
        )
        raise RuntimeError(error)

    result = subprocess.run(
        [codex_bin, "features", "list"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        error = f"Failed to query Codex CLI features: {stderr or 'unknown error'}"
        _CODEX_REQUIREMENTS_CACHE.update(
            {"checked_at": now, "ok": False, "error": error, "codex_bin": codex_bin}
        )
        raise RuntimeError(error)

    feature_line = None
    for line in result.stdout.splitlines():
        if line.strip().startswith("image_generation"):
            feature_line = line.strip()
            break

    if not feature_line or "true" not in feature_line.lower():
        error = "Codex CLI image_generation feature is unavailable. Upgrade Codex CLI and re-check auth."
        _CODEX_REQUIREMENTS_CACHE.update(
            {"checked_at": now, "ok": False, "error": error, "codex_bin": codex_bin}
        )
        raise RuntimeError(error)

    _CODEX_REQUIREMENTS_CACHE.update(
        {"checked_at": now, "ok": True, "error": None, "codex_bin": codex_bin}
    )
    return codex_bin



def _cleanup_stale_temp_dirs(
    *,
    base_dir: Optional[Path | str] = None,
    max_age_seconds: int = TEMP_DIR_MAX_AGE_SECONDS,
    now: Optional[float] = None,
    force: bool = False,
) -> int:
    global _LAST_TEMP_DIR_CLEANUP_AT

    current_time = time.time() if now is None else now
    if (
        not force
        and _LAST_TEMP_DIR_CLEANUP_AT
        and current_time - _LAST_TEMP_DIR_CLEANUP_AT < TEMP_DIR_CLEANUP_INTERVAL_SECONDS
    ):
        return 0

    _LAST_TEMP_DIR_CLEANUP_AT = current_time
    root = Path(base_dir) if base_dir is not None else Path(tempfile.gettempdir())
    if not root.exists():
        return 0

    removed = 0
    for path in root.iterdir():
        if not path.is_dir() or not path.name.startswith(TEMP_DIR_PREFIX):
            continue
        try:
            age_seconds = current_time - path.stat().st_mtime
        except OSError:
            continue
        if age_seconds <= max_age_seconds:
            continue
        shutil.rmtree(path, ignore_errors=True)
        removed += 1
    return removed



def check_codex_imagegen_requirements() -> bool:
    try:
        _ensure_codex_available()
        return True
    except Exception:
        return False



def _format_codex_error(exc: Exception) -> str:
    if not isinstance(exc, CodexImageGenerationError):
        return str(exc)

    message = f"[{exc.code}] {exc}"
    if exc.debug_paths:
        debug_pairs = ", ".join(f"{key}={value}" for key, value in sorted(exc.debug_paths.items()))
        message = f"{message} | debug: {debug_pairs}"
    return message



def run_codex_image_generation(
    prompt: str,
    aspect_ratio: str = "landscape",
    file_name: Optional[str] = None,
    output_dir: Optional[str] = None,
    background: str = "auto",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    if aspect_ratio not in VALID_ASPECT_RATIOS:
        raise ValueError(f"aspect_ratio must be one of: {', '.join(VALID_ASPECT_RATIOS)}")
    if background not in VALID_BACKGROUNDS:
        raise ValueError(f"background must be one of: {', '.join(VALID_BACKGROUNDS)}")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    codex_bin = _ensure_codex_available()

    safe_file_name = _safe_file_name(file_name)
    if output_dir:
        workdir = Path(output_dir).expanduser()
        workdir.mkdir(parents=True, exist_ok=True)
    else:
        _cleanup_stale_temp_dirs()
        workdir = Path(tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX))

    image_snapshot = _snapshot_image_files(workdir)
    codex_prompt = _build_codex_prompt(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        file_name=safe_file_name,
        background=background,
    )

    cmd = [
        codex_bin,
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "--output-last-message",
        "result.txt",
        codex_prompt,
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        debug_paths = _write_debug_artifacts(workdir, exc.stdout or "", exc.stderr or "")
        raise CodexImageGenerationError(
            "CODEX_TIMEOUT",
            f"Codex image generation timed out after {timeout_seconds} seconds.",
            debug_paths=debug_paths,
        ) from exc

    debug_paths = _write_debug_artifacts(workdir, result.stdout or "", result.stderr or "")
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or "Codex CLI exited with a non-zero status"
        raise CodexImageGenerationError(
            "CODEX_EXEC_FAILED",
            f"Codex image generation failed: {detail}",
            debug_paths=debug_paths,
        )

    try:
        image_path = _resolve_generated_file(workdir, safe_file_name, image_snapshot)
    except CodexImageGenerationError as exc:
        exc.debug_paths = {**debug_paths, **exc.debug_paths}
        raise

    return {
        "success": True,
        "image_path": str(image_path.resolve()),
        "file_name": image_path.name,
        "output_dir": str(workdir.resolve()),
        "stdout": _truncate_log_text(result.stdout or ""),
        "stderr": _truncate_log_text(result.stderr or ""),
        "stdout_path": debug_paths["stdout_path"],
        "stderr_path": debug_paths["stderr_path"],
        "result_path": debug_paths["result_path"],
        "assistant_hint": f"Send this image in Telegram with MEDIA:{image_path.resolve()}",
    }



def _handle_codex_image_generate(args, **_kwargs) -> str:
    try:
        return tool_result(
            run_codex_image_generation(
                prompt=args.get("prompt", ""),
                aspect_ratio=args.get("aspect_ratio", "landscape"),
                file_name=args.get("file_name"),
                output_dir=args.get("output_dir"),
                background=args.get("background", "auto"),
                timeout_seconds=int(args.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
            )
        )
    except Exception as exc:
        return tool_error(_format_codex_error(exc), success=False)



def _pre_llm_codex_imagegen_route(**kwargs):
    return _build_routing_context(kwargs.get("user_message"))



def _register_codex_tool(ctx) -> None:
    ctx.register_tool(
        name="codex_image_generate",
        toolset="codex_image_gen",
        schema=CODEX_IMAGE_GENERATE_SCHEMA,
        handler=_handle_codex_image_generate,
        check_fn=check_codex_imagegen_requirements,
        requires_env=[],
        is_async=False,
        description=CODEX_IMAGE_GENERATE_SCHEMA["description"],
        emoji="🎨",
    )



def _register_override_tool(ctx) -> None:
    if os.getenv(OVERRIDE_ENV_VAR, "").lower() not in {"1", "true", "yes", "on"}:
        return

    if registry.get_entry("image_generate") is not None:
        registry.deregister("image_generate")

    ctx.register_tool(
        name="image_generate",
        toolset="image_gen",
        schema=OVERRIDE_IMAGE_GENERATE_SCHEMA,
        handler=_handle_codex_image_generate,
        check_fn=check_codex_imagegen_requirements,
        requires_env=[],
        is_async=False,
        description=OVERRIDE_IMAGE_GENERATE_SCHEMA["description"],
        emoji="🎨",
    )



def register(ctx):
    _register_codex_tool(ctx)
    ctx.register_hook("pre_llm_call", _pre_llm_codex_imagegen_route)
    _register_override_tool(ctx)
