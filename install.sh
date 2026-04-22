#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="Jinbro98"
REPO_NAME="hermes-gpt-image-gen"
BRANCH="${HERMES_GPT_IMAGE_GEN_BRANCH:-main}"
PLUGIN_NAME="codex_image_gen"
DEST_DIR="${HERMES_GPT_IMAGE_GEN_DIR:-$HOME/.hermes/plugins/$PLUGIN_NAME}"
RAW_BASE="${HERMES_GPT_IMAGE_GEN_RAW_BASE:-https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/${BRANCH}}"

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command not found: $1" >&2
    exit 1
  fi
}

download() {
  local url="$1"
  local output="$2"

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$output"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$output" "$url"
  else
    echo "Error: curl or wget is required." >&2
    exit 1
  fi
}

need_cmd mkdir
need_cmd cp
need_cmd date

if [ -d "$DEST_DIR" ] && find "$DEST_DIR" -mindepth 1 -print -quit >/dev/null 2>&1; then
  BACKUP_DIR="${DEST_DIR}.bak.$(date +%Y%m%d%H%M%S)"
  cp -R "$DEST_DIR" "$BACKUP_DIR"
  echo "Backed up existing plugin to: $BACKUP_DIR"
fi

mkdir -p "$DEST_DIR"
download "$RAW_BASE/plugin.yaml" "$DEST_DIR/plugin.yaml"
download "$RAW_BASE/__init__.py" "$DEST_DIR/__init__.py"

chmod 644 "$DEST_DIR/plugin.yaml" "$DEST_DIR/__init__.py"

echo "Installed Hermes Codex image plugin to: $DEST_DIR"

echo
echo "Next steps:"
echo "1. Verify Codex image support: codex features list | grep '^image_generation'"
echo "2. Restart Hermes/gateway or start a fresh session (/reset)."
echo "3. Optional override: export HERMES_CODEX_IMAGEGEN_OVERRIDE=1 before starting Hermes."
