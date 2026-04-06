#!/bin/bash

set -euo pipefail

devkit_skill_manifest() {
  printf '%s\n' \
    dig \
    gpt-pro \
    deep-research \
    amazon-search \
    improve-skill \
    codex-search \
    devkit-init \
    repo-maintainer \
    repo-maintainer-init
}

devkit_retired_skill_entries() {
  printf '%s\n' \
    mermaid-show \
    dig-core \
    dig-claude \
    dig-codex \
    dig-opencode
}

devkit_repo_url() {
  if [[ -n "${DEVKIT_REPO_URL:-}" ]]; then
    printf '%s\n' "$DEVKIT_REPO_URL"
  else
    printf '%s\n' "https://github.com/murakotaro4/devkit.git"
  fi
}

devkit_default_source_root() {
  if [[ -n "${DEVKIT_SOURCE_ROOT:-}" ]]; then
    printf '%s\n' "$DEVKIT_SOURCE_ROOT"
    return
  fi

  local persisted_root
  persisted_root="$(devkit_read_persisted_source_root "$HOME" || true)"
  if [[ -n "$persisted_root" ]]; then
    printf '%s\n' "$persisted_root"
    return
  fi

  printf '%s\n' "$HOME/cursor/devkit"
}

devkit_source_root_state_files() {
  local user_home="${1:-$HOME}"
  printf '%s\n' \
    "$user_home/.codex/devkit/source-root.txt" \
    "$user_home/.config/opencode/devkit/source-root.txt"
}

devkit_read_persisted_source_root() {
  local user_home="${1:-$HOME}"
  local state_file

  while IFS= read -r state_file; do
    [[ -f "$state_file" ]] || continue

    local candidate
    candidate="$(head -n 1 "$state_file" | tr -d '\r' | sed 's/[[:space:]]*$//')"
    [[ -n "$candidate" ]] || continue

    local repo_root
    repo_root="$(devkit_repo_root_from_source_hint "$candidate" || true)"
    if [[ -n "$repo_root" ]]; then
      printf '%s\n' "$repo_root"
      return 0
    fi
  done < <(devkit_source_root_state_files "$user_home")

  return 1
}

devkit_persist_source_root() {
  local state_file="$1"
  local repo_root="$2"
  ensure_devkit_dir "$(dirname "$state_file")"
  printf '%s\n' "$repo_root" >"$state_file"
}

devkit_script_checkout_root() {
  [[ -n "${SCRIPT_DIR:-}" ]] || return 1

  local hint_root repo_root
  hint_root="$(cd "$SCRIPT_DIR/../../.." && pwd -P)"

  if command -v git >/dev/null 2>&1; then
    local git_root
    git_root="$(git -C "$hint_root" rev-parse --show-toplevel 2>/dev/null || true)"
    if [[ -n "$git_root" ]]; then
      repo_root="$(devkit_repo_root_from_source_hint "$git_root" || true)"
      if [[ -n "$repo_root" ]]; then
        printf '%s\n' "$repo_root"
        return 0
      fi
    fi
  fi

  repo_root="$(devkit_repo_root_from_source_hint "$hint_root" || true)"
  [[ -n "$repo_root" ]] || return 1
  [[ -e "$repo_root/.git" ]] || return 1
  printf '%s\n' "$repo_root"
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

devkit_resolve_path_lenient() {
  local path="$1"
  devkit_resolve_path "$path" 2>/dev/null && return 0
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$path"
    return
  fi
  local dir base
  dir="$(dirname "$path")"
  base="$(basename "$path")"
  if [[ -d "$dir" ]]; then
    printf '%s/%s\n' "$(cd "$dir" && pwd -P)" "$base"
  else
    printf '%s\n' "$path"
  fi
}

devkit_resolve_link_target() {
  local path="$1"
  local target
  target="$(readlink "$path")"
  if [[ "$target" != /* ]]; then
    target="$(cd "$(dirname "$path")" && cd "$(dirname "$target")" && pwd -P)/$(basename "$target")"
  fi
  devkit_resolve_path_lenient "$target"
}

ensure_devkit_dir() {
  mkdir -p "$1"
}

devkit_log() {
  if [[ $# -gt 0 ]]; then
    printf 'INFO: %s\n' "$1" >&2
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
    if ! (devkit_skill_manifest; devkit_retired_skill_entries) | grep -Fxq "$name"; then
      printf 'BLOCKED_LEGACY_SKILLS_ROOT: %s contains non-DevKit entry %s. Remediation: move custom skills out of ~/.agent/skills before migrating OpenCode.\n' "$link_target" "$name" >&2
      return 1
    fi
  done < <(find "$link_target" -mindepth 1 -maxdepth 1 2>/dev/null)
}

devkit_repo_root_from_source_hint() {
  local hint="$1"
  [[ -n "$hint" ]] || return 1

  if [[ -d "$hint/plugins/devkit" ]]; then
    devkit_resolve_path "$hint"
    return 0
  fi

  if [[ -d "$hint/skills" && -d "$hint/scripts" && -d "$hint/templates" ]]; then
    devkit_resolve_path "$(cd "$hint/../.." && pwd -P)"
    return 0
  fi

  return 1
}

ensure_devkit_repo_root() {
  local preferred_root repo_url repo_root script_root
  preferred_root="$(devkit_default_source_root)"
  repo_url="$(devkit_repo_url)"
  if [[ -n "${DEVKIT_SOURCE_ROOT:-}" ]]; then
    repo_root="$(devkit_repo_root_from_source_hint "$preferred_root" || true)"
  else
    script_root="$(devkit_script_checkout_root || true)"
    if [[ -n "$script_root" ]]; then
      repo_root="$script_root"
    else
      repo_root="$(devkit_repo_root_from_source_hint "$preferred_root" || true)"
    fi
  fi

  if [[ -z "$repo_root" ]]; then
    if [[ -e "$preferred_root" ]] && [[ -n "$(find "$preferred_root" -mindepth 1 -maxdepth 1 2>/dev/null | head -1)" ]]; then
      printf 'DEVKIT_SOURCE_ROOT_NOT_EMPTY: %s\n' "$preferred_root" >&2
      return 1
    fi

    if command -v git >/dev/null 2>&1; then
      ensure_devkit_dir "$(dirname "$preferred_root")"
      devkit_log "Cloning DevKit checkout: $preferred_root"
      if git clone --depth 1 "$repo_url" "$preferred_root" >&2; then
        repo_root="$(devkit_repo_root_from_source_hint "$preferred_root" || true)"
      else
        rm -rf "$preferred_root"
        printf 'DEVKIT_REPO_CLONE_FAILED: %s\n' "$preferred_root" >&2
        return 1
      fi
    fi
  fi

  if [[ -z "$repo_root" ]]; then
    printf 'DEVKIT_REPO_ROOT_NOT_FOUND: expected DevKit under %s\n' "$preferred_root" >&2
    return 1
  fi

  if [[ -d "$repo_root/.git" ]]; then
    if command -v git >/dev/null 2>&1; then
      devkit_log "Updating DevKit checkout: $repo_root"
      git -C "$repo_root" pull --ff-only >&2
    else
      devkit_log "git is unavailable. Reusing the existing DevKit checkout."
    fi
  elif [[ ! -d "$repo_root/plugins/devkit" ]]; then
    printf 'DEVKIT_PLUGIN_ROOT_NOT_FOUND: %s/plugins/devkit\n' "$repo_root" >&2
    return 1
  fi

  printf '%s\n' "$repo_root"
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
      expected_target="$(devkit_resolve_path_lenient "$expected_legacy_target")"
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
  shift 2

  if [[ ! -d "$source_path" ]]; then
    printf 'MISSING_SKILL_SOURCE_DIR: %s\n' "$source_path" >&2
    return 1
  fi

  if [[ -L "$destination_path" ]]; then
    local actual_target
    actual_target="$(devkit_resolve_link_target "$destination_path")"
    local expected_target
    expected_target="$(devkit_resolve_path "$source_path")"

    local is_legacy=false
    local _lt
    for _lt in "$@"; do
      [[ -z "$_lt" ]] && continue
      local resolved_lt
      resolved_lt="$(devkit_resolve_path_lenient "$_lt")"
      if [[ "$actual_target" == "$resolved_lt" ]]; then
        is_legacy=true; break
      fi
    done

    if [[ "$actual_target" != "$expected_target" && "$is_legacy" != "true" ]]; then
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

prune_devkit_managed_skill_links() {
  local skills_root="$1"
  shift

  [[ -d "$skills_root" ]] || return 0

  while IFS= read -r entry; do
    local name actual_target
    name="$(basename "$entry")"
    actual_target="$(devkit_resolve_link_target "$entry")"

    local is_managed=false
    local _i
    for _i in "$@"; do
      case "$actual_target" in "$_i"/*) is_managed=true; break ;; esac
    done
    if "$is_managed" && ! devkit_skill_manifest | grep -Fxq "$name"; then
      rm -rf "$entry"
    fi
  done < <(find "$skills_root" -mindepth 1 -maxdepth 1 -type l 2>/dev/null)
}

prune_legacy_codex_managed_entries() {
  local legacy_root="$1"
  local plugin_skills_root="$2"
  local legacy_source_skills_root="$3"
  local marketplace_skills_root="$4"
  [[ -d "$legacy_root" ]] || return 0

  while IFS= read -r entry; do
    local name actual_target
    name="$(basename "$entry")"
    if ! (devkit_skill_manifest; devkit_retired_skill_entries) | grep -Fxq "$name"; then
      continue
    fi

    actual_target="$(devkit_resolve_link_target "$entry")"
    case "$actual_target" in
      "$plugin_skills_root"/*|"$legacy_source_skills_root"/*|"$marketplace_skills_root"/*)
        rm -rf "$entry"
        ;;
    esac
  done < <(find "$legacy_root" -mindepth 1 -maxdepth 1 -type l 2>/dev/null)
}

prune_legacy_opencode_managed_entries() {
  local opencode_root="$1"
  local plugin_skills_root="$2"
  local legacy_source_skills_root="$3"
  local marketplace_skills_root="$4"
  local codex_source_skills_root="${5:-}"
  [[ -d "$opencode_root" ]] || return 0

  while IFS= read -r entry; do
    local name actual_target
    name="$(basename "$entry")"
    if ! (devkit_skill_manifest; devkit_retired_skill_entries) | grep -Fxq "$name"; then
      continue
    fi

    actual_target="$(devkit_resolve_link_target "$entry")"
    local _prune_match=false
    case "$actual_target" in
      "$plugin_skills_root"/*|"$legacy_source_skills_root"/*|"$marketplace_skills_root"/*)
        _prune_match=true
        ;;
    esac
    if [[ "$_prune_match" != "true" && -n "$codex_source_skills_root" ]]; then
      case "$actual_target" in
        "$codex_source_skills_root"/*) _prune_match=true ;;
      esac
    fi
    if [[ "$_prune_match" == "true" ]]; then
      rm -rf "$entry"
    fi
  done < <(find "$opencode_root" -mindepth 1 -maxdepth 1 -type l 2>/dev/null)
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
  local codex_skills="$user_home/.agents/skills"
  local legacy_codex_skills="$codex_root/skills"
  local codex_bin="$codex_root/bin"
  local local_bin="$user_home/.local/bin"

  local repo_root
  repo_root="$(ensure_devkit_repo_root_cached)"
  ensure_devkit_dir "$codex_root"
  ensure_devkit_dir "$codex_bin"
  ensure_directory_container "$codex_skills"

  local plugin_root="$repo_root/plugins/devkit"
  prune_legacy_codex_managed_entries \
    "$legacy_codex_skills" \
    "$plugin_root/skills" \
    "$codex_root/devkit/source/plugins/devkit/skills" \
    "$user_home/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills"
  prune_devkit_managed_skill_links "$codex_skills" \
    "$plugin_root/skills" \
    "$codex_root/devkit/source/plugins/devkit/skills" \
    "$user_home/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills"
  local skill
  while IFS= read -r skill; do
    ensure_linked_dir \
      "$plugin_root/skills/$skill" \
      "$codex_skills/$skill" \
      "$codex_root/devkit/source/plugins/devkit/skills/$skill" \
      "$user_home/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills/$skill"
  done < <(devkit_skill_manifest)

  local script_name
  for script_name in \
    devkit-runtime-sync.sh \
    update-ccx.sh \
    update-devkit.sh
  do
    ensure_managed_file \
      "$plugin_root/scripts/$script_name" \
      "$codex_bin/$script_name" \
      true
  done

  devkit_persist_source_root "$codex_root/devkit/source-root.txt" "$repo_root"
  install_devkit_shell_shim "$local_bin/update-devkit" "$codex_bin/update-devkit.sh"
  install_devkit_shell_shim "$local_bin/update-ccx" "$codex_bin/update-ccx.sh"
}

sync_devkit_opencode_runtime() {
  local user_home="$1"
  local opencode_root="$user_home/.config/opencode"
  local opencode_skills="$opencode_root/skills"
  local opencode_commands="$opencode_root/commands"

  local repo_root
  repo_root="$(ensure_devkit_repo_root_cached)"
  ensure_directory_container "$opencode_skills" "$user_home/.agent/skills" true
  ensure_directory_container "$opencode_commands"

  local plugin_root="$repo_root/plugins/devkit"
  prune_legacy_opencode_managed_entries \
    "$opencode_skills" \
    "$plugin_root/skills" \
    "$opencode_root/devkit/source/plugins/devkit/skills" \
    "$user_home/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills" \
    "$user_home/.codex/devkit/source/plugins/devkit/skills"
  prune_devkit_managed_skill_links "$opencode_skills" \
    "$plugin_root/skills" \
    "$opencode_root/devkit/source/plugins/devkit/skills" \
    "$user_home/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills" \
    "$user_home/.codex/devkit/source/plugins/devkit/skills"
  local skill
  while IFS= read -r skill; do
    ensure_linked_dir \
      "$plugin_root/skills/$skill" \
      "$opencode_skills/$skill" \
      "$user_home/.agent/skills/$skill" \
      "$opencode_root/devkit/source/plugins/devkit/skills/$skill" \
      "$user_home/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills/$skill" \
      "$user_home/.codex/devkit/source/plugins/devkit/skills/$skill"
  done < <(devkit_skill_manifest)

  ensure_managed_file \
    "$plugin_root/templates/opencode/commands/dig.md" \
    "$opencode_commands/dig.md" \
    false

  devkit_persist_source_root "$opencode_root/devkit/source-root.txt" "$repo_root"
}

_DEVKIT_CACHED_REPO_ROOT=""
ensure_devkit_repo_root_cached() {
  if [[ -n "$_DEVKIT_CACHED_REPO_ROOT" ]]; then
    printf '%s\n' "$_DEVKIT_CACHED_REPO_ROOT"
    return 0
  fi
  _DEVKIT_CACHED_REPO_ROOT="$(ensure_devkit_repo_root)"
  printf '%s\n' "$_DEVKIT_CACHED_REPO_ROOT"
}

ensure_devkit_hooks() {
  local git_root="$1"
  local hooks_dir="$git_root/.githooks"

  if [[ ! -d "$hooks_dir" ]]; then
    devkit_log "No .githooks directory found in $git_root, skipping hook setup"
    return 0
  fi

  # 既存の core.hooksPath を確認（BLOCKED パターン準拠）
  local current_hooks_path
  current_hooks_path="$(git -C "$git_root" config --local --get core.hooksPath 2>/dev/null)" || true

  if [[ -n "$current_hooks_path" ]]; then
    if [[ "$current_hooks_path" == ".githooks" ]]; then
      # 既に DevKit 管理パス — 更新不要
      return 0
    else
      printf 'BLOCKED_EXISTING_HOOKS_PATH: %s (expected .githooks or unset)\n' "$current_hooks_path" >&2
      return 1
    fi
  fi

  if ! git -C "$git_root" config core.hooksPath .githooks; then
    printf 'FAILED_HOOKS_PATH_CONFIG: git config core.hooksPath failed in %s\n' "$git_root" >&2
    return 1
  fi
  devkit_log "Configured core.hooksPath = .githooks in $git_root"
}
