# hermes-gpt-image-gen

Codex CLI-powered image generation plugin for **Hermes Agent**.

This plugin adds a new Hermes tool, `codex_image_generate`, which runs Codex CLI `$imagegen`, saves the output as a **local image file**, and returns the absolute path so Hermes can send it directly in Telegram with `MEDIA:/absolute/path`.

It also adds routing hints so explicit requests such as:

- `덕테이프로 ... 이미지 생성해줘`
- `코덱스로 ... 이미지 생성해줘`
- `gpt로 ... 이미지 생성해줘`

prefer the Codex-backed image workflow.

---

## Features

- Adds `codex_image_generate` tool to Hermes
- Uses **Codex CLI** image generation instead of a hosted image URL backend
- Returns local file paths for Telegram/media workflows
- Supports `landscape`, `square`, `portrait`
- Supports `auto`, `transparent`, `opaque` background preference
- Optional override mode: replace built-in Hermes `image_generate` with the Codex-backed implementation
- Trigger-based routing for explicit Codex/GPT image generation requests

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

## Repository layout

This repository intentionally keeps only the minimal distribution files:

```text
plugin.yaml
__init__.py
README.md
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
