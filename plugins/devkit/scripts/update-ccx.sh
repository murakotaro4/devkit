#!/bin/bash
#
# update-ccx.sh - DevKit updater.
#
# Updates Claude Code / Codex CLI and keeps the DevKit Claude/Codex plugins
# current through their plugin marketplaces.
#
# Usage:
#   update-ccx.sh              # update CLIs and DevKit plugin registrations
#   update-ccx.sh --version    # show current versions
#

set -o pipefail

declare -a ERRORS=()
declare -a WARNINGS=()
CLI_ONLY=false
DEVKIT_ONLY=false
RUN_MODE="run"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

windows_path_to_posix() {
    local input_path="$1"
    local normalized=""

    if command -v cygpath &>/dev/null; then
        normalized="$(cygpath -u "$input_path" 2>/dev/null || true)"
    fi
    if [[ -z "$normalized" && "$input_path" == /* ]]; then
        normalized="$input_path"
    fi
    if [[ -z "$normalized" ]]; then
        local slash_path="${input_path//\\//}"
        if [[ "$slash_path" =~ ^([A-Za-z]):/(.*)$ ]]; then
            normalized="/${BASH_REMATCH[1],,}/${BASH_REMATCH[2]}"
        fi
    fi

    [[ -n "$normalized" && "$normalized" == /* ]] || return 1
    printf '%s\n' "${normalized%/}"
}

source_root_path_for_shell() {
    local source_root="$1"
    case "$(uname -s)" in
        MINGW*|MSYS*)
            local normalized=""
            normalized="$(windows_path_to_posix "$source_root" || true)"
            if [[ -n "$normalized" ]]; then
                printf '%s\n' "$normalized"
                return 0
            fi
            ;;
    esac
    printf '%s\n' "$source_root"
}

source_devkit_lib_for_update() {
    local lib_path="$SCRIPT_DIR/devkit-lib.sh"
    if [[ -f "$lib_path" ]]; then
        local normal_root=""
        if [[ -f "$SCRIPT_DIR/../../../plugins/devkit/scripts/devkit-lib.sh" ]]; then
            normal_root="$(cd "$SCRIPT_DIR/../../.." && pwd)"
        elif [[ -f "$HOME/cursor/devkit/plugins/devkit/scripts/devkit-lib.sh" ]]; then
            normal_root="$HOME/cursor/devkit"
        else
            local state_file="$HOME/.codex/devkit/source-root.txt"
            if [[ -f "$state_file" ]]; then
                normal_root="$(head -n 1 "$state_file" | tr -d '\r' | sed 's/[[:space:]]*$//' || true)"
                normal_root="$(source_root_path_for_shell "$normal_root")"
            fi
        fi
        if [[ -z "${DEVKIT_SOURCE_ROOT:-}" && -n "$normal_root" ]]; then
            export DEVKIT_SOURCE_ROOT="$normal_root"
        fi
        source "$lib_path" || return 1
        return 0
    fi

    local repo_root=""
    local -a repo_candidates=()

    if [[ -n "${DEVKIT_SOURCE_ROOT:-}" ]]; then
        repo_candidates+=("$DEVKIT_SOURCE_ROOT")
    fi
    if [[ -f "$SCRIPT_DIR/../../../plugins/devkit/scripts/devkit-lib.sh" ]]; then
        repo_candidates+=("$(cd "$SCRIPT_DIR/../../.." && pwd)")
    fi
    repo_candidates+=("$HOME/cursor/devkit")

    local state_file="$HOME/.codex/devkit/source-root.txt"
    if [[ -f "$state_file" ]]; then
        repo_root="$(head -n 1 "$state_file" | tr -d '\r' | sed 's/[[:space:]]*$//' || true)"
        repo_root="$(source_root_path_for_shell "$repo_root")"
        if [[ -n "$repo_root" ]]; then
            repo_candidates+=("$repo_root")
        fi
    fi

    for repo_root in "${repo_candidates[@]}"; do
        [[ -n "$repo_root" ]] || continue
        lib_path="$repo_root/plugins/devkit/scripts/devkit-lib.sh"
        if [[ -f "$lib_path" ]]; then
            # v5 -> v6 one-time rebootstrap: old installed updaters do not know devkit-lib.sh.
            mkdir -p "$HOME/.codex/bin"
            cp "$lib_path" "$HOME/.codex/bin/devkit-lib.sh"
            if [[ -z "${DEVKIT_SOURCE_ROOT:-}" ]]; then
                export DEVKIT_SOURCE_ROOT="$repo_root"
            fi
            source "$HOME/.codex/bin/devkit-lib.sh" || return 1
            return 0
        fi
    done

    printf 'MISSING_SOURCE_FILE: %s\n' "$SCRIPT_DIR/devkit-lib.sh" >&2
    return 1
}

source_devkit_lib_for_update || exit 1

detect_os() {
    case "$(uname -s)" in
        Darwin) echo "macos" ;;
        Linux)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                echo "wsl"
            else
                echo "linux"
            fi
            ;;
        MINGW*|MSYS*) echo "windows" ;;
        *) echo "unknown" ;;
    esac
}

OS_TYPE=$(detect_os)

get_claude_version() {
    claude --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown"
}

get_codex_version() {
    codex --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown"
}

resolve_command_path() {
    local command_path="$1"

    if command -v realpath &>/dev/null; then
        realpath "$command_path" 2>/dev/null
    elif command -v greadlink &>/dev/null; then
        greadlink -f "$command_path" 2>/dev/null
    elif [[ -L "$command_path" ]]; then
        local link_target
        link_target=$(readlink "$command_path" 2>/dev/null)
        if [[ "$link_target" != /* ]]; then
            printf '%s/%s\n' "$(cd "$(dirname "$command_path")" && cd "$(dirname "$link_target")" && pwd)" "$(basename "$link_target")"
        else
            printf '%s\n' "$link_target"
        fi
    else
        printf '%s\n' "$command_path"
    fi
}

detect_claude_install() {
    local claude_path
    claude_path=$(command -v claude 2>/dev/null)

    if [[ -z "$claude_path" ]]; then
        echo "not_found"
        return
    fi

    local resolved_path
    resolved_path="$(resolve_command_path "$claude_path")"

    if [[ "$resolved_path" == *".local/share/claude/"* ]] || [[ "$resolved_path" == *".local/bin/claude"* ]]; then
        echo "native"
        return
    elif [[ "$resolved_path" == *"node_modules"* ]] || [[ "$claude_path" == *".nvm/"* ]] || [[ "$claude_path" == *".npm/"* ]] || [[ "$claude_path" == */fnm/* ]] || [[ "$resolved_path" == */fnm/* ]]; then
        echo "npm"
        return
    fi

    if [[ "$OS_TYPE" == "macos" ]] && command -v brew &>/dev/null; then
        local brew_prefix
        brew_prefix=$(brew --prefix 2>/dev/null)
        if [[ -n "$brew_prefix" ]] && [[ "$resolved_path" == "$brew_prefix"* || "$resolved_path" == "/Applications/"* ]]; then
            if brew list --cask 2>/dev/null | grep -q "^claude$"; then
                echo "homebrew-cask"
                return
            fi
        fi
    fi

    if claude update --help &>/dev/null; then
        echo "native"
    else
        echo "npm"
    fi
}

detect_codex_install() {
    local codex_path
    codex_path=$(command -v codex 2>/dev/null)

    if [[ -z "$codex_path" ]]; then
        echo "not_found"
        return
    fi

    local resolved_path
    resolved_path="$(resolve_command_path "$codex_path")"

    if [[ "$resolved_path" == *"node_modules"* ]] || [[ "$codex_path" == *".nvm/"* ]] || [[ "$codex_path" == *".npm/"* ]] || [[ "$codex_path" == */fnm/* ]] || [[ "$resolved_path" == */fnm/* ]]; then
        echo "npm"
        return
    fi

    if [[ "$OS_TYPE" == "macos" ]] && command -v brew &>/dev/null; then
        local brew_prefix
        brew_prefix=$(brew --prefix 2>/dev/null)
        if [[ -n "$brew_prefix" ]] && [[ "$resolved_path" == "$brew_prefix"* ]]; then
            if brew list --cask codex &>/dev/null 2>&1; then
                echo "homebrew-cask"
                return
            fi
            echo "brew"
            return
        fi
    fi

    if command -v npm &>/dev/null && npm list -g @openai/codex &>/dev/null 2>&1; then
        echo "npm"
        return
    fi

    echo "unknown"
}

show_versions() {
    echo "Environment: $OS_TYPE"
    echo "Claude Code: $(get_claude_version)"
    echo "Codex CLI:   $(get_codex_version)"
}

show_usage() {
    cat <<'EOF'
Usage:
  update-ccx.sh                       # update tools and DevKit plugin registrations
  update-ccx.sh --version             # show current versions
  update-ccx.sh --cli-only            # update Claude/Codex CLIs only
  update-ccx.sh --devkit-only         # update DevKit managed files and Claude/Codex plugins only
EOF
}

parse_args() {
    RUN_MODE="run"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --version|-v)
                if [[ $# -ne 1 ]]; then
                    echo "INVALID_ARGS: --version cannot be combined with other arguments" >&2
                    return 1
                fi
                RUN_MODE="version"
                return 0
                ;;
            --cli-only)
                CLI_ONLY=true
                ;;
            --devkit-only)
                DEVKIT_ONLY=true
                ;;
            *)
                echo "INVALID_ARGS: unknown argument '$1'" >&2
                return 1
                ;;
        esac
        shift
    done

    if [[ "$CLI_ONLY" == true && "$DEVKIT_ONLY" == true ]]; then
        echo "INVALID_ARGS: --cli-only and --devkit-only cannot be combined" >&2
        return 1
    fi
}

join_summary_parts() {
    local IFS=' / '
    echo "$*"
}

section_prerequisites() {
    echo ""
    echo "=== [Prerequisites] ==="

    if ! command -v curl &>/dev/null; then
        echo "ERROR: curl is not installed."
        exit 1
    fi
    echo "OK curl: available"

    local bash_major="${BASH_VERSINFO[0]}"
    if [[ "$bash_major" -lt 4 ]]; then
        echo "WARN Bash $BASH_VERSION (4.0+ recommended)"
    else
        echo "OK Bash: $BASH_VERSION"
    fi

    case "$OS_TYPE" in
        windows)
            if command -v winget &>/dev/null; then
                echo "OK winget: available"
            else
                echo "WARN winget: not found (fnm install will use curl fallback)"
            fi
            ;;
        macos)
            if command -v brew &>/dev/null; then
                echo "OK brew: $(brew --version 2>/dev/null | head -1)"
            else
                echo "WARN brew: not found (installations will use npm/curl)"
            fi
            ;;
        wsl|linux)
            echo "OK OS: $OS_TYPE (curl-based installation)"
            ;;
    esac
}

resolve_fnm_command() {
    if command -v fnm &>/dev/null; then
        return 0
    fi

    local -a fnm_dirs=("$HOME/.local/share/fnm" "$HOME/.fnm")
    if [[ "$OS_TYPE" == "windows" && -n "${LOCALAPPDATA:-}" ]]; then
        local local_app_data=""
        local_app_data="$(windows_path_to_posix "$LOCALAPPDATA" || true)"
        if [[ -n "$local_app_data" ]]; then
            fnm_dirs+=("$local_app_data/Microsoft/WinGet/Links")
        fi
    fi

    local fnm_dir
    for fnm_dir in "${fnm_dirs[@]}"; do
        if [[ -x "$fnm_dir/fnm" || -x "$fnm_dir/fnm.exe" ]]; then
            export PATH="$fnm_dir:$PATH"
            hash -r 2>/dev/null
            break
        fi
    done

    command -v fnm &>/dev/null
}

initialize_fnm_environment() {
    command -v fnm &>/dev/null || return 0
    [[ -z "${FNM_MULTISHELL_PATH:-}" ]] || return 0

    local fnm_environment=""
    if fnm_environment="$(fnm env --shell bash 2>/dev/null)" && [[ -n "$fnm_environment" ]] && eval "$fnm_environment"; then
        echo "OK fnm: non-interactive shell environment initialized"
        return 0
    fi

    echo "WARN fnm: failed to initialize the non-interactive shell environment"
    WARNINGS+=("fnm: non-interactive shell environment initialization failed")
    return 0
}

ensure_fnm() {
    if resolve_fnm_command; then
        initialize_fnm_environment
        echo "OK fnm: already installed ($(fnm --version 2>/dev/null))"
        return 0
    fi

    echo -n "Installing fnm... "
    case "$OS_TYPE" in
        windows)
            if command -v winget &>/dev/null; then
                winget install Schniz.fnm --accept-package-agreements --accept-source-agreements >/dev/null 2>&1 || \
                    curl -fsSL https://fnm.vercel.app/install | bash >/dev/null 2>&1
            else
                curl -fsSL https://fnm.vercel.app/install | bash >/dev/null 2>&1
            fi
            ;;
        macos)
            if command -v brew &>/dev/null; then
                brew install fnm >/dev/null 2>&1 || curl -fsSL https://fnm.vercel.app/install | bash >/dev/null 2>&1
            else
                curl -fsSL https://fnm.vercel.app/install | bash >/dev/null 2>&1
            fi
            ;;
        wsl|linux|*)
            curl -fsSL https://fnm.vercel.app/install | bash >/dev/null 2>&1
            ;;
    esac

    export PATH="$HOME/.local/share/fnm:$HOME/.fnm:$PATH"
    hash -r 2>/dev/null
    resolve_fnm_command || true
    initialize_fnm_environment
    if command -v fnm &>/dev/null; then
        echo "OK ($(fnm --version 2>/dev/null))"
    else
        echo "ERROR"
        ERRORS+=("fnm: installation failed")
        return 1
    fi
}

ensure_nodejs() {
    if command -v node &>/dev/null; then
        echo "OK Node.js: already installed ($(node --version 2>/dev/null))"
        return 0
    fi

    if ! command -v fnm &>/dev/null; then
        echo "ERROR Node.js: fnm not available, cannot install"
        ERRORS+=("Node.js: fnm required but not available")
        return 1
    fi

    echo -n "Installing Node.js (LTS)... "
    if fnm install --lts >/dev/null 2>&1 && fnm use --lts >/dev/null 2>&1; then
        echo "OK ($(node --version 2>/dev/null))"
    else
        echo "ERROR"
        ERRORS+=("Node.js: fnm install --lts failed")
        return 1
    fi
}

ensure_claude() {
    if command -v claude &>/dev/null; then
        echo "OK Claude Code: already installed ($(get_claude_version))"
        return 0
    fi

    echo -n "Installing Claude Code (native)... "
    case "$OS_TYPE" in
        windows)
            if powershell.exe -Command "irm https://claude.ai/install.ps1 | iex" >/dev/null 2>&1; then
                hash -r 2>/dev/null
                echo "OK"
                if ! command -v claude &>/dev/null; then
                    echo "WARN Claude Code: installed, but the command is not on PATH yet. Restart the terminal."
                    WARNINGS+=("Claude Code: restart the terminal to refresh PATH")
                fi
            else
                echo "ERROR"
                ERRORS+=("Claude Code: native install failed")
                return 1
            fi
            ;;
        macos|wsl|linux|*)
            if curl -fsSL https://claude.ai/install.sh | bash >/dev/null 2>&1; then
                export PATH="$HOME/.local/bin:$PATH"
                hash -r 2>/dev/null
                echo "OK"
            else
                echo "ERROR"
                ERRORS+=("Claude Code: native install failed")
                return 1
            fi
            ;;
    esac
}

ensure_codex() {
    if command -v codex &>/dev/null; then
        echo "OK Codex CLI: already installed ($(get_codex_version))"
        return 0
    fi

    if ! command -v npm &>/dev/null; then
        echo "ERROR Codex CLI: npm not available"
        ERRORS+=("Codex CLI: npm required but not available")
        return 1
    fi

    echo -n "Installing Codex CLI... "
    if npm install -g @openai/codex >/dev/null 2>&1; then
        echo "OK"
        hash -r 2>/dev/null
        if [[ "$OS_TYPE" == "windows" ]] && ! command -v codex &>/dev/null; then
            echo "WARN Codex CLI: installed, but the command is not on PATH yet. Restart the terminal."
            WARNINGS+=("Codex CLI: restart the terminal to refresh PATH")
        fi
    else
        echo "ERROR"
        ERRORS+=("Codex CLI: npm install failed")
        return 1
    fi
}

section_setup() {
    echo ""
    echo "=== [Setup] ==="

    if ! command -v codex &>/dev/null; then
        ensure_fnm
        ensure_nodejs
    fi
    ensure_claude
    ensure_codex
}

update_claude() {
    local install_method="$1"
    echo -n "Updating Claude Code ($install_method)... "
    case "$install_method" in
        native)
            if claude update </dev/null 2>/dev/null; then
                echo "OK"
            else
                local exit_code=$?
                echo "ERROR"
                ERRORS+=("Claude Code: claude update failed (exit code $exit_code)")
            fi
            ;;
        homebrew-cask)
            if brew upgrade --cask claude; then
                echo "OK"
            else
                local exit_code=$?
                echo "ERROR"
                ERRORS+=("Claude Code: brew upgrade --cask failed (exit code $exit_code)")
            fi
            ;;
        npm)
            if npm update -g @anthropic-ai/claude-code; then
                echo "OK"
            else
                local exit_code=$?
                echo "ERROR"
                ERRORS+=("Claude Code: npm update failed (exit code $exit_code)")
            fi
            ;;
    esac
}

update_codex() {
    local install_method="$1"
    echo -n "Updating Codex CLI ($install_method)... "
    case "$install_method" in
        npm)
            local update_output update_exit
            update_output=$(npm update -g @openai/codex 2>&1)
            update_exit=$?
            if [[ $update_exit -eq 0 ]]; then
                echo "OK"
            elif grep -qE "EBUSY|resource busy or locked" <<<"$update_output"; then
                echo "SKIPPED"
                WARNINGS+=("Codex CLI: skipped self-update because codex is locked by the current session")
            else
                echo "ERROR"
                printf '%s\n' "$update_output" >&2
                ERRORS+=("Codex CLI: npm update failed (exit code $update_exit)")
            fi
            ;;
        brew)
            if brew upgrade codex; then
                echo "OK"
            else
                local exit_code=$?
                echo "ERROR"
                ERRORS+=("Codex CLI: brew upgrade failed (exit code $exit_code)")
            fi
            ;;
        homebrew-cask)
            if brew upgrade --cask codex; then
                echo "OK"
            else
                local exit_code=$?
                echo "ERROR"
                ERRORS+=("Codex CLI: brew upgrade --cask failed (exit code $exit_code)")
            fi
            ;;
    esac
}

section_update() {
    echo ""
    echo "=== [Update] ==="

    local claude_install codex_install
    claude_install=$(detect_claude_install)
    codex_install=$(detect_codex_install)

    if [[ "$claude_install" == "not_found" ]]; then
        echo "WARN Claude Code: not installed, skipping update"
        claude_install="skip"
    fi
    if [[ "$codex_install" == "not_found" ]] || [[ "$codex_install" == "unknown" ]]; then
        echo "WARN Codex CLI: not installed, skipping update"
        codex_install="skip"
    fi

    local before_parts=(
        "claude: $(get_claude_version) ($claude_install)"
        "codex: $(get_codex_version) ($codex_install)"
    )
    echo "[Before] $(join_summary_parts "${before_parts[@]}")"

    if [[ "$claude_install" != "skip" ]]; then
        update_claude "$claude_install"
    fi
    if [[ "$codex_install" != "skip" ]]; then
        update_codex "$codex_install"
    fi

    local after_parts=(
        "claude: $(get_claude_version)"
        "codex: $(get_codex_version)"
    )
    echo "[After]  $(join_summary_parts "${after_parts[@]}")"
}

windows_path_from_posix() {
    local input_path="$1"
    command -v cygpath &>/dev/null || return 1

    local normalized=""
    normalized="$(cygpath -w "$input_path" 2>/dev/null || true)"
    [[ -n "$normalized" ]] || return 1
    printf '%s\n' "$normalized"
}

install_windows_update_shim() {
    local shim_path="$1"
    local target_command_path="$2"
    if [[ -d "$shim_path" && ! -L "$shim_path" ]]; then
        echo "BLOCKED_EXISTING_DIR: $shim_path" >&2
        return 1
    fi

    local windows_target=""
    if ! windows_target="$(windows_path_from_posix "$target_command_path")"; then
        windows_target='%USERPROFILE%\.codex\bin\update-ccx.cmd'
        echo "WARN DevKit managed file: cygpath could not resolve the installed update-ccx.cmd; using USERPROFILE fallback" >&2
        WARNINGS+=("DevKit managed file: update-ccx.cmd shim uses USERPROFILE fallback")
    fi

    mkdir -p "$(dirname "$shim_path")"
    rm -f -- "$shim_path"
    printf '@echo off\r\nsetlocal\r\ncall "%s" %%*\r\nexit /b %%ERRORLEVEL%%\r\n' "$windows_target" > "$shim_path"
}

install_windows_codex_config() {
    local config_script_path="$1"
    if ! command -v powershell.exe &>/dev/null; then
        echo "FAILED Codex config: powershell.exe is not available"
        ERRORS+=("Codex config: powershell.exe is not available")
        return 1
    fi

    local windows_config_script=""
    local windows_home=""
    if ! windows_config_script="$(windows_path_from_posix "$config_script_path")" || \
       ! windows_home="$(windows_path_from_posix "$HOME")"; then
        if [[ -z "${USERPROFILE:-}" ]]; then
            echo "FAILED Codex config: managed paths could not be converted and USERPROFILE is unavailable"
            ERRORS+=("Codex config: managed path resolution failed")
            return 1
        fi
        windows_config_script="$USERPROFILE\.codex\bin\devkit-codex-config.ps1"
        windows_home="$USERPROFILE"
        echo "WARN Codex config: cygpath could not resolve managed paths; using USERPROFILE fallback" >&2
        WARNINGS+=("Codex config: managed path resolution uses USERPROFILE fallback")
    fi

    if ! DEVKIT_CODEX_CONFIG_SCRIPT="$windows_config_script" DEVKIT_WINDOWS_HOME="$windows_home" \
      powershell.exe -NoProfile -ExecutionPolicy Bypass -Command '
$ErrorActionPreference = "Stop"
. $env:DEVKIT_CODEX_CONFIG_SCRIPT
$configResult = Install-DevKitCodexConfig -UserHome $env:DEVKIT_WINDOWS_HOME -OsName "windows"
if ($configResult.BootstrappedLocalOverlay) {
  Write-Warning "Codex config.local.toml was bootstrapped from the existing config."
}
if ($configResult.BackupPath) {
  Write-Host ("Codex config backup saved to: {0}" -f $configResult.BackupPath)
}
'; then
        echo "FAILED Codex config templating"
        ERRORS+=("Codex config: templating failed")
        return 1
    fi

    echo "OK Codex config templated"
}

remove_windows_legacy_scheduled_task() {
    local powershell_lib_path="$1"
    if ! command -v powershell.exe &>/dev/null; then
        echo "WARN DevKit migration: powershell.exe is unavailable; legacy scheduled task cleanup skipped" >&2
        WARNINGS+=("DevKit migration: legacy scheduled task cleanup skipped because powershell.exe is unavailable")
        return 0
    fi

    local windows_powershell_lib=""
    if ! windows_powershell_lib="$(windows_path_from_posix "$powershell_lib_path")"; then
        if [[ -z "${USERPROFILE:-}" ]]; then
            echo "WARN DevKit migration: devkit-lib.ps1 path could not be resolved; legacy scheduled task cleanup skipped" >&2
            WARNINGS+=("DevKit migration: legacy scheduled task cleanup skipped because devkit-lib.ps1 path resolution failed")
            return 0
        fi
        windows_powershell_lib="$USERPROFILE\.codex\bin\devkit-lib.ps1"
        echo "WARN DevKit migration: cygpath could not resolve devkit-lib.ps1; using USERPROFILE fallback" >&2
        WARNINGS+=("DevKit migration: legacy scheduled task cleanup uses USERPROFILE fallback")
    fi

    if ! DEVKIT_POWERSHELL_LIB="$windows_powershell_lib" \
      powershell.exe -NoProfile -ExecutionPolicy Bypass -Command '
$ErrorActionPreference = "Stop"
. $env:DEVKIT_POWERSHELL_LIB
Remove-DevKitLegacyScheduledTask
'; then
        echo "WARN DevKit migration: legacy scheduled task cleanup failed; continuing migration" >&2
        WARNINGS+=("DevKit migration: legacy scheduled task cleanup failed")
        return 0
    fi

    echo "OK legacy scheduled task removed"
}

section_managed_copy() {
    echo ""
    echo "=== [DevKit Managed Files] ==="

    local repo_root plugin_root plugin_scripts template_root codex_bin local_bin codex_templates script_name
    if ! repo_root="$(ensure_devkit_repo_root_cached)"; then
        ERRORS+=("DevKit checkout: update failed")
        return 1
    fi

    plugin_root="$repo_root/plugins/devkit"
    plugin_scripts="$plugin_root/scripts"
    template_root="$plugin_root/templates/codex"
    codex_bin="$HOME/.codex/bin"
    local_bin="$HOME/.local/bin"
    codex_templates="$HOME/.codex/devkit/templates/codex"

    for script_name in update-ccx.sh devkit-lib.sh; do
        if ! ensure_managed_file "$plugin_scripts/$script_name" "$codex_bin/$script_name" true; then
            ERRORS+=("DevKit managed file: failed to update $script_name")
            return 1
        fi
    done

    if [[ "$OS_TYPE" == "windows" ]]; then
        if ! ensure_managed_file "$plugin_scripts/update-ccx.cmd" "$codex_bin/update-ccx.cmd" true; then
            ERRORS+=("DevKit managed file: failed to update update-ccx.cmd")
            return 1
        fi
        for script_name in devkit-lib.ps1 devkit-setup.ps1 devkit-codex-config.ps1; do
            if ! ensure_managed_file "$plugin_scripts/$script_name" "$codex_bin/$script_name" true; then
                ERRORS+=("DevKit managed file: failed to update $script_name")
                return 1
            fi
        done
        for script_name in config.shared.toml config.windows.toml; do
            if ! ensure_managed_file "$template_root/$script_name" "$codex_templates/$script_name" true; then
                ERRORS+=("DevKit managed file: failed to update $script_name")
                return 1
            fi
        done
        if ! ensure_managed_file "$plugin_scripts/update-ccx.ps1" "$codex_bin/update-ccx.ps1" true; then
            ERRORS+=("DevKit managed file: failed to update update-ccx.ps1")
            return 1
        fi
    fi

    chmod +x "$codex_bin/update-ccx.sh"
    devkit_persist_codex_source_root "$HOME" "$repo_root"
    if [[ "$OS_TYPE" == "windows" ]]; then
        if ! install_windows_update_shim "$local_bin/update-ccx.cmd" "$codex_bin/update-ccx.cmd"; then
            ERRORS+=("DevKit managed file: failed to update update-ccx.cmd shim")
            return 1
        fi
        install_windows_codex_config "$codex_bin/devkit-codex-config.ps1" || true
    else
        if ! install_devkit_shell_shim "$local_bin/update-ccx" "$codex_bin/update-ccx.sh"; then
            ERRORS+=("DevKit managed file: failed to update update-ccx shim")
            return 1
        fi
    fi
    local legacy_path
    local -a legacy_updater_paths=(
        "$codex_bin/update-devkit.sh"
        "$codex_bin/update-devkit.ps1"
        "$codex_bin/update-devkit.cmd"
        "$local_bin/update-devkit"
        "$local_bin/update-devkit.cmd"
    )
    for legacy_path in "${legacy_updater_paths[@]}"; do
        rm -f -- "$legacy_path"
        if [[ -e "$legacy_path" || -L "$legacy_path" ]]; then
            echo "PRUNE_FAILED: $legacy_path" >&2
            ERRORS+=("DevKit managed file: failed to prune $legacy_path")
            return 1
        fi
    done
    echo "OK managed files updated"
}

codex_marketplace_section() {
    local config_file="$HOME/.codex/config.toml"
    [[ -f "$config_file" ]] || return 1

    awk '
        /^\[marketplaces\.murakotaro4\][[:space:]]*$/ { inside = 1; found = 1; next }
        /^\[/ && inside { exit }
        inside { print }
        END { if (!found) exit 1 }
    ' "$config_file"
}

codex_marketplace_state() {
    local section
    if ! section="$(codex_marketplace_section)"; then
        echo "missing"
        return
    fi

    if grep -Eq 'source_type[[:space:]]*=[[:space:]]*"?local"?' <<<"$section" || \
        grep -Eq "source_type[[:space:]]*=[[:space:]]*'?local'?" <<<"$section" || \
        grep -Eq '^[[:space:]]*path[[:space:]]*=' <<<"$section"; then
        echo "replace"
        return
    fi

    if grep -Fq 'murakotaro4/devkit' <<<"$section"; then
        echo "ok"
    else
        echo "replace"
    fi
}

run_plugin_command() {
    local description="$1"
    shift

    echo -n "$description... "
    if "$@" </dev/null; then
        echo "OK"
        return 0
    fi

    local exit_code=$?
    echo "ERROR"
    ERRORS+=("$description failed (exit code $exit_code)")
    return 1
}

claude_marketplace_state() {
    local output
    if ! output="$(claude plugin marketplace list --json </dev/null 2>/dev/null)"; then
        return 1
    fi

    if command -v python3 >/dev/null 2>&1; then
        local parsed_state
        if parsed_state="$(printf '%s\n' "$output" | python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(2)

if not isinstance(data, list):
    sys.exit(2)

matching = [item for item in data if isinstance(item, dict) and item.get("name") == "murakotaro4"]
if not matching:
    print("missing")
elif any(item.get("source") == "github" and item.get("repo") == "murakotaro4/devkit" for item in matching):
    print("ok")
else:
    print("replace")
')"; then
            printf '%s\n' "$parsed_state"
            return 0
        else
            local parse_status=$?
            if [[ $parse_status -eq 2 ]]; then
                return 2
            fi
        fi
    fi

    local marketplace_entries
    marketplace_entries="$(
        printf '%s\n' "$output" |
            tr '\n' ' ' |
            sed -E 's/}[[:space:]]*,[[:space:]]*[{]/}\
{/g' |
            grep -E '"name"[[:space:]]*:[[:space:]]*"murakotaro4"'
    )"

    if [[ -z "$marketplace_entries" ]]; then
        echo "missing"
    elif printf '%s\n' "$marketplace_entries" |
        grep -E '"source"[[:space:]]*:[[:space:]]*"github"' |
        grep -Eq '"repo"[[:space:]]*:[[:space:]]*"murakotaro4/devkit"'; then
        echo "ok"
    else
        echo "replace"
    fi
}

claude_plugin_devkit_state() {
    local output
    if ! output="$(claude plugin list --json </dev/null 2>/dev/null)"; then
        return 1
    fi

    if command -v python3 >/dev/null 2>&1; then
        local parsed_state
        if parsed_state="$(printf '%s\n' "$output" | python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(2)

if not isinstance(data, list):
    sys.exit(2)
print("installed" if any(
    isinstance(item, dict)
    and item.get("id") == "devkit@murakotaro4"
    and item.get("scope") == "user"
    for item in data
) else "missing")
')"; then
            printf '%s\n' "$parsed_state"
            return 0
        else
            local parse_status=$?
            if [[ $parse_status -eq 2 ]]; then
                return 2
            fi
        fi
    fi

    local devkit_entry
    devkit_entry="$(
        printf '%s\n' "$output" |
            tr '\n' ' ' |
            sed -E 's/}[[:space:]]*,[[:space:]]*[{]/}\
{/g' |
            grep -E '"id"[[:space:]]*:[[:space:]]*"devkit@murakotaro4"' |
            grep -E '"scope"[[:space:]]*:[[:space:]]*"user"' |
            head -n 1
    )"

    if [[ -n "$devkit_entry" ]]; then
        echo "installed"
    else
        echo "missing"
    fi
}

codex_plugin_devkit_state() {
    local output
    if ! output="$(codex plugin list --json 2>/dev/null)"; then
        echo "missing"
        return 0
    fi

    if command -v python3 >/dev/null 2>&1; then
        local parsed_state
        if parsed_state="$(printf '%s\n' "$output" | python3 -c '
import json
import sys

def disabled(value):
    return value is False or value == 0 or (isinstance(value, str) and value.lower() == "false")

def match_name(value):
    for key in ("name", "id", "plugin", "slug"):
        text = str(value.get(key, ""))
        if text == "devkit" or text.startswith("devkit@"):
            return True
    return False

def walk(value, available=False):
    if isinstance(value, dict):
        if match_name(value) and not available:
            return "disabled" if disabled(value.get("enabled")) else "enabled"
        states = [walk(item, available or key == "available") for key, item in value.items()]
    elif isinstance(value, list):
        states = [walk(item, available) for item in value]
    elif isinstance(value, str):
        if not available and (value == "devkit" or value.startswith("devkit@")):
            return "enabled"
        return "missing"
    else:
        return "missing"

    if "enabled" in states:
        return "enabled"
    if "disabled" in states:
        return "disabled"
    return "missing"

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
print(walk(data))
')"; then
            printf '%s\n' "$parsed_state"
            return 0
        fi
    fi

    local scan devkit_entry
    scan="$(printf '%s\n' "$output" | sed -E 's/"available"[[:space:]]*:[[:space:]]*\[[^]]*\]//g')"
    if grep -Eq '"installed"[[:space:]]*:' <<<"$output"; then
        scan="$(printf '%s\n' "$output" | sed -E 's/.*"installed"[[:space:]]*:[[:space:]]*\[//; s/\][[:space:]]*,[[:space:]]*"available".*//')"
    fi
    devkit_entry="$(
        printf '%s\n' "$scan" |
            tr '\n' ' ' |
            sed -E 's/}[[:space:]]*,[[:space:]]*[{]/}\
{/g' |
            grep -E '"(name|id|plugin|slug)"[[:space:]]*:[[:space:]]*"devkit"|devkit@murakotaro4' |
            head -n 1
    )"

    if [[ -z "$devkit_entry" ]]; then
        echo "missing"
    elif grep -Eq '"enabled"[[:space:]]*:[[:space:]]*(false|0|"false")' <<<"$devkit_entry"; then
        echo "disabled"
    else
        echo "enabled"
    fi
}

section_codex_plugin() {
    echo ""
    echo "=== [Codex Plugin] ==="

    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v codex &>/dev/null; then
        echo "SKIP Codex CLI is not available"
        return 0
    fi

    local state
    state="$(codex_marketplace_state)"
    case "$state" in
        missing)
            run_plugin_command \
                "Adding DevKit marketplace" \
                codex plugin marketplace add murakotaro4/devkit || return 1
            ;;
        replace)
            run_plugin_command \
                "Removing non-git DevKit marketplace" \
                codex plugin marketplace remove murakotaro4 || return 1
            run_plugin_command \
                "Adding DevKit marketplace" \
                codex plugin marketplace add murakotaro4/devkit || return 1
            ;;
        ok)
            echo "OK DevKit marketplace already registered"
            ;;
    esac

    run_plugin_command \
        "Upgrading DevKit marketplace" \
        codex plugin marketplace upgrade murakotaro4 || return 1

    run_plugin_command \
        "Installing DevKit plugin" \
        codex plugin add devkit@murakotaro4 || return 1
}

section_claude_plugin() {
    echo ""
    echo "=== [Claude Plugin] ==="

    if ! command -v claude &>/dev/null; then
        echo "SKIP Claude Code is not available"
        return 0
    fi

    local marketplace_state marketplace_status
    marketplace_state="$(claude_marketplace_state)"
    marketplace_status=$?
    if [[ $marketplace_status -ne 0 ]]; then
        if [[ $marketplace_status -eq 1 ]]; then
            ERRORS+=("Claude marketplace list failed")
        else
            ERRORS+=("Claude marketplace list JSON parse failed")
        fi
        return 1
    fi

    case "$marketplace_state" in
        ok)
            run_plugin_command \
                "Updating Claude marketplace" \
                claude plugin marketplace update murakotaro4 || return 1
            ;;
        replace)
            run_plugin_command \
                "Removing unexpected Claude marketplace" \
                claude plugin marketplace remove --scope user murakotaro4 || return 1
            run_plugin_command \
                "Adding Claude marketplace" \
                claude plugin marketplace add --scope user murakotaro4/devkit || return 1
            ;;
        missing)
            run_plugin_command \
                "Adding Claude marketplace" \
                claude plugin marketplace add --scope user murakotaro4/devkit || return 1
            ;;
    esac

    local plugin_state plugin_status
    plugin_state="$(claude_plugin_devkit_state)"
    plugin_status=$?
    if [[ $plugin_status -ne 0 ]]; then
        if [[ $plugin_status -eq 1 ]]; then
            ERRORS+=("Claude plugin list failed")
        else
            ERRORS+=("Claude plugin list JSON parse failed")
        fi
        return 1
    fi

    if [[ "$plugin_state" == "installed" ]]; then
        run_plugin_command \
            "Updating Claude DevKit plugin" \
            claude plugin update --scope user devkit@murakotaro4 || return 1
    else
        run_plugin_command \
            "Installing Claude DevKit plugin" \
            claude plugin install --scope user devkit@murakotaro4 || return 1
    fi

    echo "NOTE: Running Claude Code sessions need /reload-plugins (or restart) to apply the updated plugin."
}

section_prune_legacy_assets() {
    echo ""
    echo "=== [DevKit Migration] ==="

    local repo_root
    if ! repo_root="$(ensure_devkit_repo_root_cached)"; then
        ERRORS+=("DevKit checkout: update failed")
        return 1
    fi

    if [[ "$OS_TYPE" == "windows" && ! -f "$HOME/.codex/devkit/.migrated-v6" ]]; then
        remove_windows_legacy_scheduled_task "$HOME/.codex/bin/devkit-lib.ps1"
    fi

    if prune_legacy_devkit_assets "$HOME" "$repo_root"; then
        echo "OK legacy assets pruned"
    else
        ERRORS+=("DevKit migration: legacy asset prune failed")
        return 1
    fi
}

resolve_cursor_prune_python() {
    if python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3]))); raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' &>/dev/null; then
        printf 'python3\n'
        return 0
    fi
    if python -c 'import sys; print(".".join(map(str, sys.version_info[:3]))); raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' &>/dev/null; then
        printf 'python\n'
        return 0
    fi
    if py -3 -c 'import sys; print(".".join(map(str, sys.version_info[:3]))); raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' &>/dev/null; then
        printf 'py\n'
        return 0
    fi
    return 1
}

section_prune_cursor_sync() {
    echo ""
    echo "=== [Cursor Legacy Sync Migration] ==="

    if [[ ! -d "$HOME/.cursor" ]]; then
        echo "SKIP Cursor user directory is not available"
        return 0
    fi
    if [[ ! -e "$HOME/.cursor/.devkit-sync-manifest.json" && ! -L "$HOME/.cursor/.devkit-sync-manifest.json" ]]; then
        echo "SKIP legacy Cursor sync manifest is not available"
        return 0
    fi
    local python_kind=""
    if ! python_kind="$(resolve_cursor_prune_python)"; then
        echo "WARN Python 3.10 or newer is not available; skipping legacy Cursor sync prune"
        WARNINGS+=("Cursor legacy sync: Python 3.10 or newer not available; prune skipped")
        return 0
    fi

    local -a python_command=("$python_kind")
    if [[ "$python_kind" == "py" ]]; then
        python_command=(py -3)
    fi

    local repo_root prune_output
    if ! repo_root="$(ensure_devkit_repo_root_cached)"; then
        ERRORS+=("Cursor legacy sync: DevKit checkout unavailable")
        return 1
    fi

    if ! prune_output="$("${python_command[@]}" "$repo_root/plugins/devkit/skills/setup/scripts/prune_legacy_cursor_sync.py" \
        --target "$HOME/.cursor" \
        --format json)"; then
        echo "FAILED legacy Cursor sync prune"
        ERRORS+=("Cursor legacy sync: prune failed")
        return 1
    fi

    echo "$prune_output"
}

main() {
    if ! parse_args "$@"; then
        show_usage
        exit 1
    fi

    if [[ "$RUN_MODE" == "version" ]]; then
        show_versions
        exit 0
    fi

    echo "=== Claude Code, Codex CLI & DevKit ==="
    echo "Environment: $OS_TYPE"

    if [[ "$CLI_ONLY" != true ]]; then
        section_managed_copy
    fi

    if [[ "$DEVKIT_ONLY" != true ]]; then
        section_prerequisites
        section_setup
        section_update
    fi

    if [[ "$CLI_ONLY" != true ]]; then
        section_prune_legacy_assets
        section_prune_cursor_sync
        section_codex_plugin
        section_claude_plugin
    fi

    echo ""

    if [[ ${#WARNINGS[@]} -gt 0 ]]; then
        echo "Warnings:"
        local warn
        for warn in "${WARNINGS[@]}"; do
            echo "  - $warn"
        done
    fi

    if [[ ${#ERRORS[@]} -eq 0 ]]; then
        echo "OK All done"
    else
        echo "Errors occurred:"
        local err
        for err in "${ERRORS[@]}"; do
            echo "  - $err"
        done
        exit 1
    fi
}

main "$@"
