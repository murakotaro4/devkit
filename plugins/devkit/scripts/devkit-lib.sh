#!/bin/bash

devkit_repo_url() {
  if [[ -n "${DEVKIT_REPO_URL:-}" ]]; then
    printf '%s\n' "$DEVKIT_REPO_URL"
  else
    printf '%s\n' "https://github.com/murakotaro4/devkit.git"
  fi
}

devkit_codex_source_root_state_file() {
  local user_home="${1:-$HOME}"
  printf '%s\n' "$user_home/.codex/devkit/source-root.txt"
}

devkit_is_windows_posix_shell() {
  case "$(uname -s)" in
    MINGW*|MSYS*) return 0 ;;
    *) return 1 ;;
  esac
}

devkit_source_root_to_shell_path() {
  local source_root="$1"
  if ! devkit_is_windows_posix_shell; then
    printf '%s\n' "$source_root"
    return 0
  fi

  local normalized=""
  if declare -F windows_path_to_posix >/dev/null 2>&1; then
    normalized="$(windows_path_to_posix "$source_root" 2>/dev/null || true)"
  elif command -v cygpath >/dev/null 2>&1; then
    normalized="$(cygpath -u "$source_root" 2>/dev/null || true)"
  fi
  if [[ -z "$normalized" && "$source_root" == /* ]]; then
    normalized="$source_root"
  fi
  if [[ -z "$normalized" ]]; then
    local slash_path="${source_root//\\//}"
    if [[ "$slash_path" =~ ^([A-Za-z]):/(.*)$ ]]; then
      normalized="/${BASH_REMATCH[1],,}/${BASH_REMATCH[2]}"
    fi
  fi

  [[ -n "$normalized" ]] || return 1
  printf '%s\n' "${normalized%/}"
}

devkit_source_root_to_state_path() {
  local source_root="$1"
  if ! devkit_is_windows_posix_shell; then
    printf '%s\n' "$source_root"
    return 0
  fi

  local normalized=""
  if declare -F windows_path_from_posix >/dev/null 2>&1; then
    normalized="$(windows_path_from_posix "$source_root" 2>/dev/null || true)"
  elif command -v cygpath >/dev/null 2>&1; then
    normalized="$(cygpath -w "$source_root" 2>/dev/null || true)"
  fi
  [[ -n "$normalized" ]] || return 1
  printf '%s\n' "$normalized"
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

devkit_read_persisted_source_root() {
  local user_home="${1:-$HOME}"
  local state_file
  state_file="$(devkit_codex_source_root_state_file "$user_home")"
  [[ -f "$state_file" ]] || return 1

  local candidate
  candidate="$(head -n 1 "$state_file" | tr -d '\r' | sed 's/[[:space:]]*$//')"
  [[ -n "$candidate" ]] || return 1
  candidate="$(devkit_source_root_to_shell_path "$candidate" || true)"
  [[ -n "$candidate" ]] || return 1

  local repo_root
  repo_root="$(devkit_repo_root_from_source_hint "$candidate" || true)"
  [[ -n "$repo_root" ]] || return 1
  printf '%s\n' "$repo_root"
}

devkit_persist_codex_source_root() {
  local user_home="$1"
  local repo_root="$2"
  local state_file state_root
  state_file="$(devkit_codex_source_root_state_file "$user_home")"
  ensure_devkit_dir "$(dirname "$state_file")"
  state_root="$(devkit_source_root_to_state_path "$repo_root" || true)"
  if [[ -z "$state_root" ]]; then
    state_root="$repo_root"
    printf 'WARN DevKit source root: could not convert checkout path to Windows format; persisting POSIX path fallback\n' >&2
    if [[ "$(declare -p WARNINGS 2>/dev/null || true)" == "declare -a"* ]]; then
      WARNINGS+=("DevKit source root: Windows path conversion failed; persisted POSIX fallback")
    fi
  fi
  printf '%s\n' "$state_root" >"$state_file"
}

devkit_script_checkout_root() {
  [[ -n "${SCRIPT_DIR:-}" ]] || return 1

  local hint_root repo_root
  hint_root="$(cd "$SCRIPT_DIR/../../.." && pwd)"
  hint_root="$(devkit_resolve_path "$hint_root")"

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
import os
import sys

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
  target="$(readlink "$path")" || return 1
  if [[ "$target" != /* ]]; then
    target="$(dirname "$path")/$target"
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
      local symbolic_ref_status
      if git -C "$repo_root" symbolic-ref -q HEAD >/dev/null; then
        symbolic_ref_status=0
      else
        symbolic_ref_status=$?
      fi

      if [[ "$symbolic_ref_status" -eq 0 ]]; then
        devkit_log "Updating DevKit checkout: $repo_root"
        if ! git -C "$repo_root" pull --ff-only >&2; then
          printf 'DEVKIT_REPO_PULL_FAILED: %s\n' "$repo_root" >&2
          return 1
        fi
      elif [[ "$symbolic_ref_status" -eq 1 ]]; then
        devkit_log "Detached HEAD checkout. Reusing the existing DevKit checkout."
      else
        printf 'DEVKIT_REPO_PULL_FAILED: %s\n' "$repo_root" >&2
        return 1
      fi
    else
      devkit_log "git is unavailable. Reusing the existing DevKit checkout."
    fi
  elif [[ ! -d "$repo_root/plugins/devkit" ]]; then
    printf 'DEVKIT_PLUGIN_ROOT_NOT_FOUND: %s/plugins/devkit\n' "$repo_root" >&2
    return 1
  fi

  printf '%s\n' "$repo_root"
}

_DEVKIT_CACHED_REPO_ROOT=""
ensure_devkit_repo_root_cached() {
  if [[ -n "$_DEVKIT_CACHED_REPO_ROOT" ]]; then
    printf '%s\n' "$_DEVKIT_CACHED_REPO_ROOT"
    return 0
  fi

  if ! _DEVKIT_CACHED_REPO_ROOT="$(ensure_devkit_repo_root)"; then
    _DEVKIT_CACHED_REPO_ROOT=""
    return 1
  fi
  printf '%s\n' "$_DEVKIT_CACHED_REPO_ROOT"
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

  local resolved_source resolved_destination
  resolved_source="$(devkit_resolve_path_lenient "$source_path")"
  resolved_destination="$(devkit_resolve_path_lenient "$destination_path")"
  if [[ "$resolved_source" == "$resolved_destination" ]]; then
    return 0
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

devkit_legacy_skill_entry_name() {
  case "$1" in
    amazon-search|codex-impl|codex-search|computer-use-chatgpt-pro|deep-research)
      return 0
      ;;
    decomposition|devkit-init|dig|dig-claude|dig-codex|dig-core|dig-cursor)
      return 0
      ;;
    discord-ops|discord-rust-server-ops|gpt-pro|improve-skill|mermaid-show|repo-maintainer)
      return 0
      ;;
    repo-maintainer-init)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

devkit_path_is_devkit_source() {
  local path
  path="$(devkit_resolve_path_lenient "$1")"
  case "$path" in
    */plugins/devkit/skills|*/plugins/devkit/skills/*)
      return 0
      ;;
    */.codex/devkit/source/plugins/devkit/skills|*/.codex/devkit/source/plugins/devkit/skills/*)
      return 0
      ;;
    */.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills|*/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills/*)
      return 0
      ;;
    */.codex/plugins/cache/murakotaro4/devkit/plugins/devkit/skills|*/.codex/plugins/cache/murakotaro4/devkit/plugins/devkit/skills/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

devkit_dir_contains_only_legacy_skill_entries() {
  local directory="$1"
  [[ -d "$directory" ]] || return 1

  local entry name
  while IFS= read -r entry; do
    name="$(basename "$entry")"
    [[ "$name" == .* ]] && continue
    if ! devkit_legacy_skill_entry_name "$name"; then
      return 1
    fi
  done < <(find "$directory" -mindepth 1 -maxdepth 1 2>/dev/null)

  return 0
}

devkit_prune_skill_root() {
  local skills_root="$1"

  if [[ -L "$skills_root" ]]; then
    local container_target
    container_target="$(devkit_resolve_link_target "$skills_root")"
    if devkit_path_is_devkit_source "$container_target" || devkit_dir_contains_only_legacy_skill_entries "$container_target"; then
      rm -f "$skills_root"
      ensure_devkit_dir "$skills_root"
    fi
    return 0
  fi

  [[ -d "$skills_root" ]] || return 0

  local entry target
  while IFS= read -r entry; do
    target="$(devkit_resolve_link_target "$entry")"
    if devkit_path_is_devkit_source "$target"; then
      rm -f "$entry"
    fi
  done < <(find "$skills_root" -mindepth 1 -maxdepth 1 -type l 2>/dev/null)
}

devkit_prune_legacy_skill_roots() {
  local user_home="$1"
  local skills_root
  for skills_root in \
    "$user_home/.agents/skills" \
    "$user_home/.codex/skills" \
    "$user_home/.agent/skills" \
    "$user_home/.config/opencode/skills"
  do
    devkit_prune_skill_root "$skills_root"
  done
}

devkit_v9_retired_skill_entry_is_managed() {
  local entry="$1"
  local retired_name="$2"

  if [[ -L "$entry" ]]; then
    local target
    target="$(devkit_resolve_link_target "$entry")" || return 1
    devkit_path_is_devkit_source "$target"
    return
  fi

  local skill_file="$entry/SKILL.md"
  [[ -d "$entry" && -f "$skill_file" ]] || return 1

  awk -v expected="$retired_name" '
    NR == 1 {
      sub(/\r$/, "")
      if ($0 != "---") exit 1
      next
    }
    {
      line = $0
      sub(/\r$/, "", line)
      if (!closed) {
        if (line == "---") {
          closed = 1
          next
        }
        if (line ~ /^[[:space:]]*name[[:space:]]*:[[:space:]]*/) {
          name_count++
          sub(/^[[:space:]]*name[[:space:]]*:[[:space:]]*/, "", line)
          sub(/[[:space:]]*$/, "", line)
          if ((substr(line, 1, 1) == "\"" && substr(line, length(line), 1) == "\"") ||
              (substr(line, 1, 1) == "\047" && substr(line, length(line), 1) == "\047")) {
            line = substr(line, 2, length(line) - 2)
          }
          matched = (line == expected)
        }
        next
      }
      if (index(line, "devkit リポジトリの `AGENTS.md`") != 0) body_marker = 1
    }
    END {
      if (!closed || name_count != 1 || !matched || !body_marker) exit 1
    }
  ' "$skill_file"
}

devkit_prune_v9_retired_skill_dirs() {
  local user_home="$1"
  local skills_root retired_name retired_entry
  for skills_root in \
    "$user_home/.agents/skills" \
    "$user_home/.codex/skills" \
    "$user_home/.agent/skills" \
    "$user_home/.config/opencode/skills"
  do
    for retired_name in dig goal-prompt; do
      retired_entry="$skills_root/$retired_name"
      if devkit_v9_retired_skill_entry_is_managed "$retired_entry" "$retired_name"; then
        rm -rf -- "$retired_entry" || return 1
      fi
    done
  done
}

devkit_prune_legacy_command_assets() {
  local user_home="$1"
  local legacy_config_root="$user_home/.config/opencode"
  local legacy_runtime="${legacy_config_root##*/}"
  local command_file="$legacy_config_root/commands/dig.md"

  if [[ -f "$command_file" ]] && grep -q "runtime=$legacy_runtime" "$command_file"; then
    rm -f "$command_file"
  fi
  rm -rf "$legacy_config_root/devkit"
}

devkit_unset_legacy_hooks_path() {
  local git_root="$1"
  [[ -d "$git_root/.git" ]] || return 0
  command -v git >/dev/null 2>&1 || return 0

  local hooks_path
  hooks_path="$(git -C "$git_root" config --local --get core.hooksPath 2>/dev/null || true)"
  if [[ "$hooks_path" == ".githooks" ]]; then
    git -C "$git_root" config --local --unset core.hooksPath >/dev/null 2>&1 || true
  fi
}

devkit_prune_marketplace_hooks() {
  local user_home="$1"
  local candidate
  for candidate in \
    "$user_home/.claude/plugins/marketplaces/murakotaro4" \
    "$user_home/.codex/plugins/cache/murakotaro4" \
    "$user_home/.codex/plugins/cache/murakotaro4/devkit"
  do
    devkit_unset_legacy_hooks_path "$candidate"
  done
}

devkit_prune_legacy_bin_assets() {
  local user_home="$1"
  local codex_bin="$user_home/.codex/bin"
  local -a legacy_updater_paths=(
    "$codex_bin/update-devkit.sh"
    "$codex_bin/update-devkit.ps1"
    "$codex_bin/update-devkit.cmd"
    "$user_home/.local/bin/update-devkit"
    "$user_home/.local/bin/update-devkit.cmd"
  )

  rm -f \
    "$codex_bin/devkit-runtime-sync.sh" \
    "$codex_bin/devkit-runtime-sync.ps1" \
    "$codex_bin/devkit-skill-update.ps1" \
    "$codex_bin/devkit-skill-update.cmd" \
    "$user_home/.local/bin/devkit-skill-update" \
    "${legacy_updater_paths[@]}"
}

prune_legacy_devkit_assets() {
  local user_home="${1:-$HOME}"
  local repo_root="${2:-}"
  local marker="$user_home/.codex/devkit/.migrated-v6"
  local v9_marker="$user_home/.codex/devkit/.migrated-v9-dig-goal"

  ensure_devkit_dir "$(dirname "$v9_marker")" || return 1
  if [[ ! -f "$v9_marker" ]]; then
    devkit_prune_v9_retired_skill_dirs "$user_home" || return 1
    printf 'migrated-v9-dig-goal\n' >"$v9_marker" || return 1
  fi

  if [[ -f "$marker" ]]; then
    return 0
  fi

  if [[ -z "$repo_root" ]]; then
    repo_root="$(ensure_devkit_repo_root_cached)"
  fi

  devkit_prune_legacy_skill_roots "$user_home"
  devkit_prune_legacy_command_assets "$user_home"
  devkit_persist_codex_source_root "$user_home" "$repo_root"
  devkit_prune_marketplace_hooks "$user_home"
  devkit_prune_legacy_bin_assets "$user_home"
  printf 'migrated-v6\n' >"$marker"
}
