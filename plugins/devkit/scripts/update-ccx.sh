#!/bin/bash
#
# update-ccx.sh - Claude Code, Codex CLI & opencode セットアップ＆アップデート
#
# Windows PowerShell / cmd users should use update-ccx.ps1 or update-ccx.cmd.
#
# 対応環境: macOS (Homebrew / npm) / WSL (native / npm) / Linux / Windows (Git Bash)
#
# Usage:
#   update-ccx.sh           # セットアップ（未インストールならインストール）＋更新
#   update-ccx.sh --version # 現在のバージョンを表示
#

set -o pipefail

# エラー収集用配列
declare -a ERRORS=()

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
    ensure_fnm
    ensure_nodejs
    ensure_claude
    ensure_codex
    ensure_opencode
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
            if npm update -g @openai/codex; then
                echo "✓"
            else
                local exit_code=$?
                echo "✗"
                ERRORS+=("Codex CLI: npm update failed (exit code $exit_code)")
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
    claude_install=$(detect_claude_install)
    codex_install=$(detect_codex_install)
    opencode_install=$(detect_opencode_install)

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

    # 更新前バージョン表示
    echo "[Before] claude: $(get_claude_version) ($claude_install) / codex: $(get_codex_version) ($codex_install) / opencode: $(get_opencode_version) ($opencode_install)"

    # 各ツールの更新
    [[ "$claude_install" != "skip" ]] && update_claude "$claude_install"
    [[ "$codex_install" != "skip" ]] && update_codex "$codex_install"
    [[ "$opencode_install" != "skip" ]] && update_opencode "$opencode_install"

    # 更新後バージョン表示
    echo "[After]  claude: $(get_claude_version) / codex: $(get_codex_version) / opencode: $(get_opencode_version)"
}

# ============================================================
# メイン処理
# ============================================================
main() {
    # --version オプション
    if [[ "$1" == "--version" ]] || [[ "$1" == "-v" ]]; then
        show_versions
        exit 0
    fi

    echo "=== Claude Code, Codex CLI & opencode ==="
    echo "Environment: $OS_TYPE"

    section_prerequisites
    section_setup
    section_update

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
