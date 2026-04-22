#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="Jinbro98"
REPO_NAME="hermes-gpt-image-gen"
BRANCH="${HERMES_GPT_IMAGE_GEN_BRANCH:-main}"
PLUGIN_NAME="codex_image_gen"
RAW_BASE="${HERMES_GPT_IMAGE_GEN_RAW_BASE:-https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/${BRANCH}}"
EXPLICIT_DEST_DIR="${HERMES_GPT_IMAGE_GEN_DIR:-}"

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

get_hermes_root() {
  local hermes_home="${HERMES_HOME:-}"

  if [ -n "$hermes_home" ]; then
    if [ "$(basename "$(dirname "$hermes_home")")" = "profiles" ]; then
      dirname "$(dirname "$hermes_home")"
      return
    fi
    echo "$hermes_home"
    return
  fi

  echo "$HOME/.hermes"
}

install_into_dir() {
  local dest_dir="$1"
  local backup_dir

  if [ -d "$dest_dir" ] && find "$dest_dir" -mindepth 1 -print -quit >/dev/null 2>&1; then
    backup_dir="${dest_dir}.bak.$(date +%Y%m%d%H%M%S)"
    cp -R "$dest_dir" "$backup_dir"
    echo "Backed up existing plugin to: $backup_dir"
  fi

  mkdir -p "$dest_dir"
  download "$RAW_BASE/plugin.yaml" "$dest_dir/plugin.yaml"
  download "$RAW_BASE/__init__.py" "$dest_dir/__init__.py"
  chmod 644 "$dest_dir/plugin.yaml" "$dest_dir/__init__.py"
  echo "Installed Hermes Codex image plugin to: $dest_dir"
}

need_cmd mkdir
need_cmd cp
need_cmd date
need_cmd find
need_cmd dirname

if [ -n "$EXPLICIT_DEST_DIR" ]; then
  install_into_dir "$EXPLICIT_DEST_DIR"
else
  HERMES_ROOT="$(get_hermes_root)"
  install_into_dir "$HERMES_ROOT/plugins/$PLUGIN_NAME"

  if [ -d "$HERMES_ROOT/profiles" ]; then
    while IFS= read -r profile_dir; do
      install_into_dir "$profile_dir/plugins/$PLUGIN_NAME"
    done < <(find "$HERMES_ROOT/profiles" -mindepth 1 -maxdepth 1 -type d | sort)
  fi
fi

echo
echo "Next steps:"
echo "1. Verify Codex image support: codex features list | grep '^image_generation'"
echo "2. Restart Hermes/gateway or start a fresh session (/reset)."
echo "3. Optional override: export HERMES_CODEX_IMAGEGEN_OVERRIDE=1 before starting Hermes."
echo "4. To install into only one custom location, set HERMES_GPT_IMAGE_GEN_DIR=/path/to/plugins/$PLUGIN_NAME before running the installer."
