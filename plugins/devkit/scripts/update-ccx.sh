#!/bin/bash
#
# update-ccx.sh - update-devkit の互換 alias。Claude Code / Codex CLI / opencode 更新 + DevKit runtime sync
#
# Windows PowerShell / cmd users should use update-ccx.ps1 or update-ccx.cmd.
#
# 対応環境: macOS (Homebrew / npm) / WSL (native / npm) / Linux / Windows (Git Bash)
#
# Usage:
#   update-devkit.sh           # 推奨: CLI 更新 + DevKit runtime sync
#   update-ccx.sh              # 互換 alias
#   update-devkit.sh --version # 現在のバージョンを表示
#

set -o pipefail

# エラー収集用配列
declare -a ERRORS=()
declare -a WARNINGS=()
CLI_ONLY=false
DEVKIT_ONLY=false
RUNTIME_SELECTION="all"
RUN_MODE="run"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/devkit-runtime-sync.sh"

# ============================================================
# OS検出
# ============================================================
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

# ============================================================
# バージョン取得関数
# ============================================================
get_claude_version() {
    claude --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown"
}

get_codex_version() {
    codex --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown"
}

get_opencode_version() {
    opencode --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown"
}

# ============================================================
# インストール方法検出関数（既存ロジック維持）
# ============================================================

# Claude Code のインストール方法を検出
detect_claude_install() {
    local claude_path
    claude_path=$(command -v claude 2>/dev/null)

    if [[ -z "$claude_path" ]]; then
        echo "not_found"
        return
    fi

    # シンボリックリンクを解決して判定（macOS/Linux対応）
    local resolved_path
    if command -v realpath &>/dev/null; then
        resolved_path=$(realpath "$claude_path" 2>/dev/null)
    elif command -v greadlink &>/dev/null; then
        resolved_path=$(greadlink -f "$claude_path" 2>/dev/null)
    elif [[ -L "$claude_path" ]]; then
        local link_target
        link_target=$(readlink "$claude_path" 2>/dev/null)
        if [[ "$link_target" != /* ]]; then
            resolved_path="$(cd "$(dirname "$claude_path")" && cd "$(dirname "$link_target")" && pwd)/$(basename "$link_target")"
        else
            resolved_path="$link_target"
        fi
    else
        resolved_path="$claude_path"
    fi

    # パスベースで判定
    if [[ "$resolved_path" == *".local/share/claude/"* ]] || [[ "$resolved_path" == *".local/bin/claude"* ]]; then
        echo "native"
        return
    elif [[ "$resolved_path" == *"node_modules"* ]] || [[ "$claude_path" == *".nvm/"* ]] || [[ "$claude_path" == *".npm/"* ]] || [[ "$claude_path" == */fnm/* ]] || [[ "$resolved_path" == */fnm/* ]]; then
        echo "npm"
        return
    fi

    # macOS: Homebrew Cask チェック
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

    # フォールバック
    if claude update --help &>/dev/null; then
        echo "native"
    else
        echo "npm"
    fi
}

# Codex CLI のインストール方法を検出
detect_codex_install() {
    local codex_path
    codex_path=$(command -v codex 2>/dev/null)

    if [[ -z "$codex_path" ]]; then
        echo "not_found"
        return
    fi

    local resolved_path
    if command -v realpath &>/dev/null; then
        resolved_path=$(realpath "$codex_path" 2>/dev/null)
    elif command -v greadlink &>/dev/null; then
        resolved_path=$(greadlink -f "$codex_path" 2>/dev/null)
    elif [[ -L "$codex_path" ]]; then
        local link_target
        link_target=$(readlink "$codex_path" 2>/dev/null)
        if [[ "$link_target" != /* ]]; then
            resolved_path="$(cd "$(dirname "$codex_path")" && cd "$(dirname "$link_target")" && pwd)/$(basename "$link_target")"
        else
            resolved_path="$link_target"
        fi
    else
        resolved_path="$codex_path"
    fi

    if [[ "$resolved_path" == *"node_modules"* ]] || [[ "$codex_path" == *".nvm/"* ]] || [[ "$codex_path" == *".npm/"* ]] || [[ "$codex_path" == */fnm/* ]] || [[ "$resolved_path" == */fnm/* ]]; then
        echo "npm"
        return
    fi

    if [[ "$OS_TYPE" == "macos" ]] && command -v brew &>/dev/null; then
        local brew_prefix
        brew_prefix=$(brew --prefix 2>/dev/null)
        if [[ -n "$brew_prefix" ]] && [[ "$resolved_path" == "$brew_prefix"* ]]; then
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

# opencode のインストール方法を検出
detect_opencode_install() {
    local opencode_path
    opencode_path=$(command -v opencode 2>/dev/null)

    if [[ -z "$opencode_path" ]]; then
        echo "not_found"
        return
    fi

    local resolved_path
    if command -v realpath &>/dev/null; then
        resolved_path=$(realpath "$opencode_path" 2>/dev/null)
    elif command -v greadlink &>/dev/null; then
        resolved_path=$(greadlink -f "$opencode_path" 2>/dev/null)
    elif [[ -L "$opencode_path" ]]; then
        local link_target
        link_target=$(readlink "$opencode_path" 2>/dev/null)
        if [[ "$link_target" != /* ]]; then
            resolved_path="$(cd "$(dirname "$opencode_path")" && cd "$(dirname "$link_target")" && pwd)/$(basename "$link_target")"
        else
            resolved_path="$link_target"
        fi
    else
        resolved_path="$opencode_path"
    fi

    if [[ "$resolved_path" == *"node_modules"* ]] || [[ "$opencode_path" == *".nvm/"* ]] || [[ "$opencode_path" == *".npm/"* ]] || [[ "$opencode_path" == */fnm/* ]] || [[ "$resolved_path" == */fnm/* ]]; then
        echo "npm"
        return
    fi

    if [[ "$OS_TYPE" == "macos" ]] && command -v brew &>/dev/null; then
        local brew_prefix
        brew_prefix=$(brew --prefix 2>/dev/null)
        if [[ -n "$brew_prefix" ]] && [[ "$resolved_path" == "$brew_prefix"* ]]; then
            if brew list opencode &>/dev/null 2>&1; then
                echo "brew:opencode"
                return
            elif brew list opencode-ai &>/dev/null 2>&1; then
                echo "brew:opencode-ai"
                return
            fi
        fi
    fi

    if command -v npm &>/dev/null && npm list -g opencode-ai &>/dev/null 2>&1; then
        echo "npm"
        return
    fi

    echo "unknown"
}

# ============================================================
# バージョン表示モード
# ============================================================
show_versions() {
    echo "Environment: $OS_TYPE"
    echo "Claude Code: $(get_claude_version)"
    echo "Codex CLI:   $(get_codex_version)"
    echo "opencode:    $(get_opencode_version)"
}

show_usage() {
    cat <<'EOF'
Usage:
  update-devkit.sh                    # preferred name: update tools and DevKit runtimes
  update-ccx.sh                       # compatibility alias
  update-devkit.sh --version          # show current versions
  update-devkit.sh --cli-only         # update Claude/Codex/OpenCode only
  update-devkit.sh --devkit-only      # sync DevKit-managed Codex/OpenCode assets only
  update-devkit.sh --runtime codex    # update only Codex CLI + Codex-managed assets
  update-devkit.sh --runtime opencode # update only OpenCode CLI + OpenCode-managed assets
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
            --runtime)
                shift
                if [[ $# -eq 0 ]]; then
                    echo "INVALID_ARGS: --runtime requires codex, opencode, or all" >&2
                    return 1
                fi
                case "$1" in
                    codex|opencode|all)
                        RUNTIME_SELECTION="$1"
                        ;;
                    *)
                        echo "INVALID_ARGS: --runtime requires codex, opencode, or all" >&2
                        return 1
                        ;;
                esac
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

    RUN_MODE="run"
}

should_manage_claude_runtime() {
    [[ "$RUNTIME_SELECTION" == "all" ]]
}

should_manage_codex_runtime() {
    [[ "$RUNTIME_SELECTION" == "all" || "$RUNTIME_SELECTION" == "codex" ]]
}

should_manage_opencode_runtime() {
    [[ "$RUNTIME_SELECTION" == "all" || "$RUNTIME_SELECTION" == "opencode" ]]
}

join_summary_parts() {
    local IFS=' / '
    echo "$*"
}

# ============================================================
# [Prerequisites] セクション
# ============================================================
section_prerequisites() {
    echo ""
    echo "=== [Prerequisites] ==="

    # curl
    if ! command -v curl &>/dev/null; then
        echo "✗ curl is not installed."
        exit 1
    fi
    echo "✓ curl: available"

    # Bash version
    local bash_major="${BASH_VERSINFO[0]}"
    if [[ "$bash_major" -lt 4 ]]; then
        echo "⚠ Bash $BASH_VERSION (4.0+ recommended)"
    else
        echo "✓ Bash: $BASH_VERSION"
    fi

    # Package manager
    case "$OS_TYPE" in
        windows)
            if command -v winget &>/dev/null; then
                echo "✓ winget: available"
            else
                echo "⚠ winget: not found (fnm install will use curl fallback)"
            fi
            ;;
        macos)
            if command -v brew &>/dev/null; then
                echo "✓ brew: $(brew --version 2>/dev/null | head -1)"
            else
                echo "⚠ brew: not found (installations will use npm/curl)"
            fi
            ;;
        wsl|linux)
            echo "✓ OS: $OS_TYPE (curl-based installation)"
            ;;
    esac
}

# ============================================================
# [Setup] セクション - ensure_* 関数群
# ============================================================

ensure_fnm() {
    if command -v fnm &>/dev/null; then
        echo "✓ fnm: already installed ($(fnm --version 2>/dev/null))"
        return 0
    fi
    echo -n "Installing fnm... "
    case "$OS_TYPE" in
        windows)
            if command -v winget &>/dev/null; then
                if winget install Schniz.fnm --accept-package-agreements --accept-source-agreements >/dev/null 2>&1; then
                    :
                else
                    curl -fsSL https://fnm.vercel.app/install | bash >/dev/null 2>&1
                fi
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
    # fnm を現在のセッションで有効化（curl installer は ~/.local/share/fnm に配置）
    export PATH="$HOME/.local/share/fnm:$HOME/.fnm:$PATH"
    eval "$(fnm env --use-on-cd --shell bash 2>/dev/null)" 2>/dev/null
    if command -v fnm &>/dev/null; then
        echo "✓ ($(fnm --version 2>/dev/null))"
    else
        echo "✗"
        ERRORS+=("fnm: installation failed")
        return 1
    fi
}

ensure_nodejs() {
    if command -v node &>/dev/null; then
        echo "✓ Node.js: already installed ($(node --version 2>/dev/null))"
        return 0
    fi
    if ! command -v fnm &>/dev/null; then
        echo "✗ Node.js: fnm not available, cannot install"
        ERRORS+=("Node.js: fnm required but not available")
        return 1
    fi
    echo -n "Installing Node.js (LTS)... "
    if fnm install --lts >/dev/null 2>&1 && fnm use --lts >/dev/null 2>&1; then
        echo "✓ ($(node --version 2>/dev/null))"
    else
        echo "✗"
        ERRORS+=("Node.js: fnm install --lts failed")
        return 1
    fi
}

ensure_claude() {
    if command -v claude &>/dev/null; then
        echo "✓ Claude Code: already installed ($(get_claude_version))"
        return 0
    fi
    echo -n "Installing Claude Code (native)... "
    case "$OS_TYPE" in
        windows)
            if powershell.exe -Command "irm https://claude.ai/install.ps1 | iex" >/dev/null 2>&1; then
                # PATH を再読み込み
                hash -r 2>/dev/null
                echo "✓"
            else
                echo "✗"
                ERRORS+=("Claude Code: native install failed")
                return 1
            fi
            ;;
        macos|wsl|linux|*)
            if curl -fsSL https://claude.ai/install.sh | bash >/dev/null 2>&1; then
                # PATH を再読み込み
                export PATH="$HOME/.local/bin:$PATH"
                hash -r 2>/dev/null
                echo "✓"
            else
                echo "✗"
                ERRORS+=("Claude Code: native install failed")
                return 1
            fi
            ;;
    esac
}

ensure_codex() {
    if command -v codex &>/dev/null; then
        echo "✓ Codex CLI: already installed ($(get_codex_version))"
        return 0
    fi
    if ! command -v npm &>/dev/null; then
        echo "✗ Codex CLI: npm not available"
        ERRORS+=("Codex CLI: npm required but not available")
        return 1
    fi
    echo -n "Installing Codex CLI... "
    if npm install -g @openai/codex >/dev/null 2>&1; then
        echo "✓"
    else
        echo "✗"
        ERRORS+=("Codex CLI: npm install failed")
        return 1
    fi
}

ensure_opencode() {
    if command -v opencode &>/dev/null; then
        echo "✓ opencode: already installed ($(get_opencode_version))"
        return 0
    fi
    echo -n "Installing opencode... "
    local install_ok=false
    # macOS: brew を優先
    if [[ "$OS_TYPE" == "macos" ]] && command -v brew &>/dev/null; then
        if brew install opencode-ai >/dev/null 2>&1; then
            echo "✓ (via brew)"
            install_ok=true
        else
            echo -n "brew failed, trying npm... "
        fi
    fi
    # npm フォールバック
    if [[ "$install_ok" == false ]]; then
        if command -v npm &>/dev/null; then
            if npm_config_optional=true npm install -g opencode-ai >/dev/null 2>&1; then
                echo "✓ (via npm)"
            else
                echo "✗"
                ERRORS+=("opencode: installation failed")
                return 1
            fi
        else
            echo "✗ No package manager available"
            ERRORS+=("opencode: no package manager available")
            return 1
        fi
    fi
}

section_setup() {
    echo ""
    echo "=== [Setup] ==="
    if should_manage_codex_runtime || should_manage_opencode_runtime; then
        ensure_fnm
        ensure_nodejs
    fi
    if should_manage_claude_runtime; then
        ensure_claude
    fi
    if should_manage_codex_runtime; then
        ensure_codex
    fi
    if should_manage_opencode_runtime; then
        ensure_opencode
    fi
}

# ============================================================
# [Update] セクション - 更新関数群
# ============================================================

update_claude() {
    local install_method="$1"
    echo -n "Updating Claude Code ($install_method)... "
    case "$install_method" in
        native)
            if claude update </dev/null 2>/dev/null; then
                echo "✓"
            else
                local exit_code=$?
                echo "✗"
                ERRORS+=("Claude Code: claude update failed (exit code $exit_code)")
            fi
            ;;
        homebrew-cask)
            if brew upgrade --cask claude; then
                echo "✓"
            else
                local exit_code=$?
                echo "✗"
                ERRORS+=("Claude Code: brew upgrade --cask failed (exit code $exit_code)")
            fi
            ;;
        npm)
            if npm update -g @anthropic-ai/claude-code; then
                echo "✓"
            else
                local exit_code=$?
                echo "✗"
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
            local update_output
            local update_exit
            update_output=$(npm update -g @openai/codex 2>&1)
            update_exit=$?
            if [[ $update_exit -eq 0 ]]; then
                echo "✓"
            elif grep -qE "EBUSY|resource busy or locked" <<<"$update_output"; then
                echo "SKIPPED"
                WARNINGS+=("Codex CLI: skipped self-update because codex is locked by the current session")
            else
                echo "✗"
                printf '%s\n' "$update_output" >&2
                ERRORS+=("Codex CLI: npm update failed (exit code $update_exit)")
            fi
            ;;
        brew)
            if brew upgrade codex; then
                echo "✓"
            else
                local exit_code=$?
                echo "✗"
                ERRORS+=("Codex CLI: brew upgrade failed (exit code $exit_code)")
            fi
            ;;
    esac
}

update_opencode() {
    local install_method="$1"
    echo -n "Updating opencode ($install_method)... "
    case "$install_method" in
        npm)
            local update_output
            local update_exit
            update_output=$(npm update -g opencode-ai 2>&1)
            update_exit=$?

            if [[ $update_exit -eq 0 ]]; then
                echo "✓"
            elif grep -qF -- "Could not find package" <<<"$update_output"; then
                echo -n "(reinstalling) "
                local install_output
                local install_exit
                install_output=$(npm_config_optional=true npm install -g opencode-ai 2>&1)
                install_exit=$?
                if [[ $install_exit -eq 0 ]]; then
                    echo "✓"
                else
                    echo "✗"
                    printf '%s\n' "$install_output" >&2
                    ERRORS+=("opencode: reinstall failed (exit code $install_exit)")
                fi
            else
                echo "✗"
                printf '%s\n' "$update_output" >&2
                ERRORS+=("opencode: npm update failed (exit code $update_exit)")
            fi
            ;;
        brew:opencode)
            if brew upgrade opencode; then
                echo "✓"
            else
                local exit_code=$?
                echo "✗"
                ERRORS+=("opencode: brew upgrade opencode failed (exit code $exit_code)")
            fi
            ;;
        brew:opencode-ai)
            if brew upgrade opencode-ai; then
                echo "✓"
            else
                local exit_code=$?
                echo "✗"
                ERRORS+=("opencode: brew upgrade opencode-ai failed (exit code $exit_code)")
            fi
            ;;
    esac
}

section_update() {
    echo ""
    echo "=== [Update] ==="

    # Setup 後に detect_* を再実行して正しいインストール方法を取得
    local claude_install codex_install opencode_install
    claude_install="skip"
    codex_install="skip"
    opencode_install="skip"
    if should_manage_claude_runtime; then
        claude_install=$(detect_claude_install)
    fi
    if should_manage_codex_runtime; then
        codex_install=$(detect_codex_install)
    fi
    if should_manage_opencode_runtime; then
        opencode_install=$(detect_opencode_install)
    fi

    # Setup でインストール失敗したツールはスキップ
    if [[ "$claude_install" == "not_found" ]]; then
        echo "⚠ Claude Code: not installed, skipping update"
        claude_install="skip"
    fi
    if [[ "$codex_install" == "not_found" ]] || [[ "$codex_install" == "unknown" ]]; then
        echo "⚠ Codex CLI: not installed, skipping update"
        codex_install="skip"
    fi
    if [[ "$opencode_install" == "not_found" ]] || [[ "$opencode_install" == "unknown" ]]; then
        echo "⚠ opencode: not installed, skipping update"
        opencode_install="skip"
    fi

    local before_parts=()
    if should_manage_claude_runtime; then
        before_parts+=("claude: $(get_claude_version) ($claude_install)")
    fi
    if should_manage_codex_runtime; then
        before_parts+=("codex: $(get_codex_version) ($codex_install)")
    fi
    if should_manage_opencode_runtime; then
        before_parts+=("opencode: $(get_opencode_version) ($opencode_install)")
    fi
    echo "[Before] $(join_summary_parts "${before_parts[@]}")"

    # 各ツールの更新
    if [[ "$claude_install" != "skip" ]]; then
        update_claude "$claude_install"
    fi
    if [[ "$codex_install" != "skip" ]]; then
        update_codex "$codex_install"
    fi
    if [[ "$opencode_install" != "skip" ]]; then
        update_opencode "$opencode_install"
    fi

    local after_parts=()
    if should_manage_claude_runtime; then
        after_parts+=("claude: $(get_claude_version)")
    fi
    if should_manage_codex_runtime; then
        after_parts+=("codex: $(get_codex_version)")
    fi
    if should_manage_opencode_runtime; then
        after_parts+=("opencode: $(get_opencode_version)")
    fi
    echo "[After]  $(join_summary_parts "${after_parts[@]}")"
}

section_devkit_sync() {
    echo ""
    echo "=== [DevKit Sync] ==="

    export PATH="$HOME/.local/bin:$PATH"

    if [[ "$RUNTIME_SELECTION" == "all" || "$RUNTIME_SELECTION" == "codex" ]]; then
        if sync_devkit_codex_runtime "$HOME"; then
            echo "✓ Codex runtime synced"
        else
            echo "✗ Codex runtime sync failed"
            ERRORS+=("Codex runtime sync failed")
        fi
    fi

    if [[ "$RUNTIME_SELECTION" == "all" || "$RUNTIME_SELECTION" == "opencode" ]]; then
        if sync_devkit_opencode_runtime "$HOME"; then
            echo "✓ OpenCode runtime synced"
        else
            echo "✗ OpenCode runtime sync failed"
            ERRORS+=("OpenCode runtime sync failed")
        fi
    fi

    # marketplace repo の hook を設定
    # shim 経由実行時 SCRIPT_DIR は runtime clone を指すため、
    # marketplace repo は既知の固定パスで参照する
    local marketplace_root="$HOME/.claude/plugins/marketplaces/murakotaro4"
    if [[ -d "$marketplace_root/.git" ]]; then
        if ensure_devkit_hooks "$marketplace_root"; then
            echo "✓ Marketplace hooks configured"
        else
            echo "✗ Marketplace hooks setup failed"
            ERRORS+=("Marketplace hooks setup failed (see BLOCKED_EXISTING_HOOKS_PATH above)")
        fi
    fi
}

# ============================================================
# メイン処理
# ============================================================
main() {
    if ! parse_args "$@"; then
        show_usage
        exit 1
    fi

    if [[ "$RUN_MODE" == "version" ]]; then
        show_versions
        exit 0
    fi

    echo "=== Claude Code, Codex CLI, opencode & DevKit ==="
    echo "Environment: $OS_TYPE"

    if [[ "$DEVKIT_ONLY" != true ]]; then
        section_prerequisites
        section_setup
        section_update
    fi

    if [[ "$CLI_ONLY" != true ]]; then
        section_devkit_sync
    fi

    echo ""

    # 結果サマリー
    if [[ ${#ERRORS[@]} -eq 0 ]]; then
        echo "✓ All done"
    else
        echo "⚠ Errors occurred:"
        for err in "${ERRORS[@]}"; do
            echo "  - $err"
        done
        exit 1
    fi
}

main "$@"
