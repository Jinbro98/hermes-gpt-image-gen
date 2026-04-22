# hermes-gpt-image-gen

[한국어](README.ko.md)

[![Release](https://img.shields.io/github/v/release/Jinbro98/hermes-gpt-image-gen?display_name=tag)](https://github.com/Jinbro98/hermes-gpt-image-gen/releases)
[![License](https://img.shields.io/github/license/Jinbro98/hermes-gpt-image-gen)](LICENSE)
[![Hermes Agent](https://img.shields.io/badge/Hermes-Agent-7C3AED)](https://github.com/Jinbro98/hermes-gpt-image-gen)
[![Codex CLI](https://img.shields.io/badge/Codex%20CLI-imagegen-10A37F)](https://developers.openai.com/codex/cli/features/)

Codex CLI-powered image generation plugin for **Hermes Agent**.

This plugin adds a new Hermes tool, `codex_image_generate`, which runs Codex CLI `$imagegen`, saves the output as a **local image file**, and returns the absolute path so Hermes can reuse it in CLI/local workflows or send it directly in Telegram with `MEDIA:/absolute/path`.

It also adds routing hints so explicit requests such as:

- `덕테이프로 ... 이미지 생성해줘`
- `코덱스로 ... 이미지 생성해줘`
- `gpt로 ... 이미지 생성해줘`

prefer the Codex-backed image workflow.

---

## Preview

### Install demo

![Install demo](assets/install-demo.gif)

### Install screenshot

![Install screenshot](assets/install-screenshot.png)

---

## Features

- Adds `codex_image_generate` tool to Hermes
- Uses **Codex CLI** image generation instead of a hosted image URL backend
- Returns local file paths for Telegram, CLI, and other Hermes workflows
- Supports `landscape`, `square`, `portrait`
- Supports `auto`, `transparent`, `opaque` background preference
- Optional override mode: replace built-in Hermes `image_generate` with the Codex-backed implementation
- Trigger-based routing for explicit Codex/GPT image generation requests
- Caches Codex capability checks to avoid repeated `codex features list` calls on hot paths
- Resolves output files more safely by tracking only **new or changed** generated images in the workdir
- Renames a single fallback image to the requested filename when it is safe to do so
- Writes `stdout`, `stderr`, and `result.txt` debug artifacts to disk for post-mortem debugging
- Cleans up stale auto-created temp workdirs on a throttled interval
- Includes pytest coverage for caching, output resolution, debug artifacts, and temp-dir cleanup

---

## Requirements

Before installing this plugin, make sure:

1. **Hermes Agent** is already installed
2. **Codex CLI** is installed and available in `PATH`
3. Codex image generation is enabled
4. Codex authentication is valid

Recommended checks:

```bash
codex --version
codex features list | grep '^image_generation'
```

Expected feature output should include something like:

```bash
image_generation stable true
```

If authentication is broken, re-login first:

```bash
codex logout
codex login
```

---

## One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/Jinbro98/hermes-gpt-image-gen/main/install.sh | bash
```

After installation, restart Hermes or start a fresh session so the plugin is loaded.

---

## Manual install

```bash
mkdir -p ~/.hermes/plugins/codex_image_gen
curl -fsSL https://raw.githubusercontent.com/Jinbro98/hermes-gpt-image-gen/main/plugin.yaml -o ~/.hermes/plugins/codex_image_gen/plugin.yaml
curl -fsSL https://raw.githubusercontent.com/Jinbro98/hermes-gpt-image-gen/main/__init__.py -o ~/.hermes/plugins/codex_image_gen/__init__.py
```

Then restart Hermes or reset the session.

---

## Usage

Once loaded, Hermes can call:

- `codex_image_generate`

Example tool payload:

```json
{
  "prompt": "Create a flat-color tangerine icon with a transparent background.",
  "aspect_ratio": "square",
  "background": "transparent",
  "file_name": "tangerine.png"
}
```

Successful output includes:

- `image_path`
- `file_name`
- `output_dir`
- `stdout_path`
- `stderr_path`
- `result_path`

Example Telegram delivery:

```text
MEDIA:/absolute/path/to/tangerine.png
```

---

## Trigger phrases

This plugin injects routing context for explicit Codex/GPT-style image requests.

Examples:

- `코덱스로 칠판 이미지 생성해줘`
- `gpt로 귤 아이콘 만들어줘`
- `덕테이프로 강아지 일러스트 제작해줘`

The routing hint activates only when:

- the message contains an engine phrase such as `덕테이프로`, `코덱스로`, or `gpt로`
- and it also looks like an actual image-generation request

---

## Optional: replace built-in `image_generate`

If you want Codex CLI to replace Hermes' built-in `image_generate`, set this **before Hermes starts**:

```bash
export HERMES_CODEX_IMAGEGEN_OVERRIDE=1
```

With that environment variable enabled, the plugin deregisters the existing `image_generate` tool and registers the Codex-backed implementation under the same name.

---

## Optional environment variables

These environment variables are optional, but useful when you want to tune reliability behavior:

```bash
# Enable override mode
export HERMES_CODEX_IMAGEGEN_OVERRIDE=1

# Cache Codex capability checks for 5 minutes (default: 300)
export HERMES_CODEX_IMAGEGEN_REQUIREMENTS_TTL=300

# Delete auto-created temp workdirs older than 24 hours (default: 86400)
export HERMES_CODEX_IMAGEGEN_TEMP_DIR_MAX_AGE=86400

# Run stale temp-dir cleanup at most once per hour (default: 3600)
export HERMES_CODEX_IMAGEGEN_CLEANUP_INTERVAL=3600
```

---

## Reliability notes

### Safer output resolution

The plugin now snapshots existing image files before invoking Codex and only accepts **new or changed** image outputs after the run. This prevents stale files in a reused output directory from being mistaken for the latest generation.

If Codex creates exactly one new image file but ignores the requested filename, the plugin renames that file to the requested filename when the extension is compatible. If Codex leaves behind multiple new image files without the expected filename, the run fails with an explicit ambiguity error instead of silently picking the newest file.

### Debug artifacts

Every Codex run now writes these artifacts into the output directory:

- `codex.stdout.log`
- `codex.stderr.log`
- `result.txt`

Their absolute paths are returned in the tool result as `stdout_path`, `stderr_path`, and `result_path`.

### Temp workdir cleanup

When `output_dir` is omitted, the plugin still creates a fresh temp directory, but it now also cleans up stale temp workdirs on a throttled interval so old generations do not accumulate forever.

---

## Testing

Run the test suite with:

```bash
pytest tests/test_plugin.py -q
```

---

## Repository layout

This repository intentionally keeps only the minimal distribution files plus tests:

```text
assets/
  install-demo.gif
  install-screenshot.png
tests/
  test_plugin.py
plugin.yaml
__init__.py
README.md
README.ko.md
install.sh
LICENSE
```

---

## Troubleshooting

### Plugin installed but Hermes does not use it

Restart Hermes/gateway or begin a fresh session.

### `Codex CLI not found in PATH`

Make sure `codex` is installed and accessible from the same environment where Hermes runs.

### `image_generation` not available

Upgrade Codex CLI and verify auth again.

### Codex returns auth errors

Try:

```bash
codex logout
codex login
```

---

## License

MIT
