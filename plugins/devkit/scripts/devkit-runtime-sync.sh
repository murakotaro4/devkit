#!/bin/bash

set -euo pipefail

devkit_skill_manifest() {
  printf '%s\n' \
    dig \
    dig-core \
    dig-claude \
    dig-codex \
    dig-opencode \
    gpt-pro \
    deep-research \
    mermaid-show \
    amazon-search \
    improve-skill \
    codex-search \
    devkit-init
}

devkit_repo_url() {
  if [[ -n "${DEVKIT_REPO_URL:-}" ]]; then
    printf '%s\n' "$DEVKIT_REPO_URL"
  else
    printf '%s\n' "https://github.com/murakotaro4/devkit.git"
  fi
}

devkit_resolve_path() {
  local path="$1"
  if command -v realpath >/dev/null 2>&1; then
    realpath "$path"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    python3 - "$path" <<'PY'
import os, sys
print(os.path.realpath(sys.argv[1]))
PY
    return
  fi

  local dir
  dir="$(cd "$(dirname "$path")" && pwd -P)"
  printf '%s/%s\n' "$dir" "$(basename "$path")"
}

devkit_resolve_link_target() {
  local path="$1"
  local target
  target="$(readlink "$path")"
  if [[ "$target" != /* ]]; then
    target="$(cd "$(dirname "$path")" && cd "$(dirname "$target")" && pwd -P)/$(basename "$target")"
  fi
  devkit_resolve_path "$target"
}

ensure_devkit_dir() {
  mkdir -p "$1"
}

devkit_log() {
  if [[ $# -gt 0 ]]; then
    printf 'INFO: %s\n' "$1"
  fi
}

ensure_devkit_checkout() {
  local source_root="$1"
  local repo_url
  repo_url="$(devkit_repo_url)"

  if [[ -d "$source_root/.git" ]]; then
    if command -v git >/dev/null 2>&1; then
      devkit_log "Updating DevKit checkout: $source_root"
      git -C "$source_root" pull --ff-only
    else
      devkit_log "git is unavailable. Reusing the existing DevKit checkout."
    fi
  elif [[ -d "$source_root/plugins/devkit" ]]; then
    devkit_log "Using the existing DevKit source snapshot: $source_root"
  else
    if [[ -e "$source_root" ]] && [[ -n "$(find "$source_root" -mindepth 1 -maxdepth 1 2>/dev/null | head -1)" ]]; then
      printf 'DEVKIT_SOURCE_ROOT_NOT_EMPTY: %s\n' "$source_root" >&2
      return 1
    fi

    if ! command -v git >/dev/null 2>&1; then
      printf 'DEVKIT_GIT_REQUIRED: git is required to fetch %s\n' "$repo_url" >&2
      return 1
    fi

    ensure_devkit_dir "$(dirname "$source_root")"
    devkit_log "Cloning DevKit checkout: $source_root"
    git clone --depth 1 "$repo_url" "$source_root"
  fi

  if [[ ! -d "$source_root/plugins/devkit" ]]; then
    printf 'DEVKIT_PLUGIN_ROOT_NOT_FOUND: %s/plugins/devkit\n' "$source_root" >&2
    return 1
  fi
}

assert_legacy_skills_root_migratable() {
  local link_target="$1"
  [[ -d "$link_target" ]] || return 0

  local entry
  while IFS= read -r entry; do
    local name
    name="$(basename "$entry")"
    [[ "$name" == .* ]] && continue
    if ! devkit_skill_manifest | grep -Fxq "$name"; then
      printf 'BLOCKED_LEGACY_SKILLS_ROOT: %s contains non-DevKit entry %s. Remediation: move custom skills out of ~/.agent/skills before migrating OpenCode.\n' "$link_target" "$name" >&2
      return 1
    fi
  done < <(find "$link_target" -mindepth 1 -maxdepth 1 2>/dev/null)
}

ensure_directory_container() {
  local path="$1"
  local expected_legacy_target="${2:-}"
  local assert_legacy="${3:-false}"

  if [[ -L "$path" ]]; then
    local actual_target
    actual_target="$(devkit_resolve_link_target "$path")"
    local expected_target=""
    if [[ -n "$expected_legacy_target" ]]; then
      expected_target="$(devkit_resolve_path "$expected_legacy_target")"
    fi

    if [[ -z "$expected_target" || "$actual_target" != "$expected_target" ]]; then
      printf 'BLOCKED_EXISTING_LINK: %s => %s\n' "$path" "$actual_target" >&2
      return 1
    fi

    if [[ "$assert_legacy" == "true" ]]; then
      assert_legacy_skills_root_migratable "$expected_legacy_target"
    fi

    rm -rf "$path"
    mkdir -p "$path"
    return 0
  fi

  if [[ -e "$path" && ! -d "$path" ]]; then
    printf 'BLOCKED_EXISTING_FILE: %s\n' "$path" >&2
    return 1
  fi

  mkdir -p "$path"
}

ensure_linked_dir() {
  local source_path="$1"
  local destination_path="$2"
  local expected_legacy_target="${3:-}"

  if [[ ! -d "$source_path" ]]; then
    printf 'MISSING_SKILL_SOURCE_DIR: %s\n' "$source_path" >&2
    return 1
  fi

  if [[ -L "$destination_path" ]]; then
    local actual_target
    actual_target="$(devkit_resolve_link_target "$destination_path")"
    local expected_target
    expected_target="$(devkit_resolve_path "$source_path")"
    local legacy_target=""
    if [[ -n "$expected_legacy_target" && -e "$expected_legacy_target" ]]; then
      legacy_target="$(devkit_resolve_path "$expected_legacy_target")"
    fi

    if [[ "$actual_target" != "$expected_target" && ( -z "$legacy_target" || "$actual_target" != "$legacy_target" ) ]]; then
      printf 'BLOCKED_EXISTING_LINK: %s => %s\n' "$destination_path" "$actual_target" >&2
      return 1
    fi

    rm -rf "$destination_path"
  elif [[ -e "$destination_path" ]]; then
    printf 'BLOCKED_EXISTING_DIR: %s\n' "$destination_path" >&2
    return 1
  fi

  ln -s "$source_path" "$destination_path"
}

ensure_managed_file() {
  local source_path="$1"
  local destination_path="$2"
  local allow_different="${3:-false}"

  if [[ ! -f "$source_path" ]]; then
    printf 'MISSING_SOURCE_FILE: %s\n' "$source_path" >&2
    return 1
  fi

  if [[ -e "$destination_path" && ! -f "$destination_path" ]]; then
    printf 'BLOCKED_EXISTING_DIR: %s\n' "$destination_path" >&2
    return 1
  fi

  if [[ -f "$destination_path" && "$allow_different" != "true" ]] && ! cmp -s "$source_path" "$destination_path"; then
    printf 'BLOCKED_EXISTING_FILE: %s\n' "$destination_path" >&2
    return 1
  fi

  ensure_devkit_dir "$(dirname "$destination_path")"
  cp "$source_path" "$destination_path"
}

install_devkit_shell_shim() {
  local shim_path="$1"
  local target_script="$2"
  ensure_devkit_dir "$(dirname "$shim_path")"
  cat >"$shim_path" <<EOF
#!/bin/bash
set -euo pipefail
exec "$target_script" "\$@"
EOF
  chmod +x "$shim_path"
}

sync_devkit_codex_runtime() {
  local user_home="$1"
  local codex_root="$user_home/.codex"
  local codex_skills="$codex_root/skills"
  local codex_devkit="$codex_root/devkit"
  local codex_source_root="$codex_devkit/source"
  local codex_source_root_file="$codex_devkit/source-root.txt"
  local local_bin="$user_home/.local/bin"

  ensure_devkit_checkout "$codex_source_root"
  ensure_directory_container "$codex_skills"

  local plugin_root="$codex_source_root/plugins/devkit"
  local skill
  while IFS= read -r skill; do
    ensure_linked_dir \
      "$plugin_root/skills/$skill" \
      "$codex_skills/$skill" \
      "$user_home/.agent/skills/$skill"
  done < <(devkit_skill_manifest)

  printf '%s\n' "$codex_source_root" >"$codex_source_root_file"
  install_devkit_shell_shim "$local_bin/update-devkit" "$plugin_root/scripts/update-devkit.sh"
  install_devkit_shell_shim "$local_bin/update-ccx" "$plugin_root/scripts/update-ccx.sh"
}

sync_devkit_opencode_runtime() {
  local user_home="$1"
  local opencode_root="$user_home/.config/opencode"
  local opencode_skills="$opencode_root/skills"
  local opencode_commands="$opencode_root/commands"
  local opencode_devkit="$opencode_root/devkit"
  local opencode_source_root="$opencode_devkit/source"
  local opencode_source_root_file="$opencode_devkit/source-root.txt"

  ensure_devkit_checkout "$opencode_source_root"
  ensure_directory_container "$opencode_skills" "$user_home/.agent/skills" true
  ensure_directory_container "$opencode_commands"

  local plugin_root="$opencode_source_root/plugins/devkit"
  local skill
  while IFS= read -r skill; do
    ensure_linked_dir \
      "$plugin_root/skills/$skill" \
      "$opencode_skills/$skill" \
      "$user_home/.agent/skills/$skill"
  done < <(devkit_skill_manifest)

  ensure_managed_file \
    "$plugin_root/templates/opencode/commands/dig.md" \
    "$opencode_commands/dig.md" \
    false

  printf '%s\n' "$opencode_source_root" >"$opencode_source_root_file"
}
