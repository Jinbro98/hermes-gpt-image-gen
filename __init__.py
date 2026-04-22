from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
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



def _find_generated_file(workdir: Path, expected_name: str) -> Optional[Path]:
    expected_path = workdir / expected_name
    if expected_path.exists():
        return expected_path

    candidates = [
        path
        for path in workdir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))



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



def _ensure_codex_available() -> None:
    codex_bin = shutil.which("codex")
    if not codex_bin:
        raise RuntimeError("Codex CLI not found in PATH.")

    result = subprocess.run(
        [codex_bin, "features", "list"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Failed to query Codex CLI features: {stderr or 'unknown error'}")

    feature_line = None
    for line in result.stdout.splitlines():
        if line.strip().startswith("image_generation"):
            feature_line = line.strip()
            break

    if not feature_line or "true" not in feature_line.lower():
        raise RuntimeError(
            "Codex CLI image_generation feature is unavailable. Upgrade Codex CLI and re-check auth."
        )



def check_codex_imagegen_requirements() -> bool:
    try:
        _ensure_codex_available()
        return True
    except Exception:
        return False



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

    _ensure_codex_available()

    safe_file_name = _safe_file_name(file_name)
    if output_dir:
        workdir = Path(output_dir).expanduser()
        workdir.mkdir(parents=True, exist_ok=True)
    else:
        workdir = Path(tempfile.mkdtemp(prefix="hermes-codex-imagegen-"))

    codex_prompt = _build_codex_prompt(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        file_name=safe_file_name,
        background=background,
    )

    cmd = [
        shutil.which("codex") or "codex",
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "--output-last-message",
        "result.txt",
        codex_prompt,
    ]
    result = subprocess.run(
        cmd,
        cwd=str(workdir),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or "Codex CLI exited with a non-zero status"
        raise RuntimeError(f"Codex image generation failed: {detail}")

    image_path = _find_generated_file(workdir, safe_file_name)
    if image_path is None:
        raise FileNotFoundError(
            f"Codex CLI finished without leaving an image file in {workdir}"
        )

    return {
        "success": True,
        "image_path": str(image_path),
        "file_name": image_path.name,
        "output_dir": str(workdir),
        "stdout": _truncate_log_text(result.stdout or ""),
        "stderr": _truncate_log_text(result.stderr or ""),
        "assistant_hint": f"Send this image in Telegram with MEDIA:{image_path}",
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
        return tool_error(str(exc), success=False)



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
