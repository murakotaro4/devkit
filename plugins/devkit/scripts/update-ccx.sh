#!/bin/bash
#
# update-ccx.sh - Claude Code, Codex CLI & opencode 一括アップデートスクリプト
#
# 対応環境: macOS (Homebrew / npm) / WSL (native / npm) / Windows (Git Bash)
#
# Usage:
#   update-ccx.sh           # 全ツールを更新
#   update-ccx.sh --version # 現在のバージョンを表示
#

set -o pipefail

# エラー収集用配列
declare -a ERRORS=()

# OS検出
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

# バージョン取得関数
get_claude_version() {
    claude --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown"
}

get_codex_version() {
    codex --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown"
}

get_opencode_version() {
    opencode --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown"
}

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
        # macOS標準readlink（-fなし）でシンボリックリンクのターゲットを取得
        local link_target
        link_target=$(readlink "$claude_path" 2>/dev/null)
        # 相対パスの場合はdirname を使って絶対パスに変換
        if [[ "$link_target" != /* ]]; then
            resolved_path="$(cd "$(dirname "$claude_path")" && cd "$(dirname "$link_target")" && pwd)/$(basename "$link_target")"
        else
            resolved_path="$link_target"
        fi
    else
        resolved_path="$claude_path"
    fi

    # パスベースで判定（最優先: PATH上のバイナリの実際の場所）
    if [[ "$resolved_path" == *".local/share/claude/"* ]] || [[ "$resolved_path" == *".local/bin/claude"* ]]; then
        echo "native"
        return
    elif [[ "$resolved_path" == *"node_modules"* ]] || [[ "$claude_path" == *".nvm/"* ]] || [[ "$claude_path" == *".npm/"* ]] || [[ "$claude_path" == */fnm/* ]] || [[ "$resolved_path" == */fnm/* ]]; then
        echo "npm"
        return
    fi

    # macOS: Homebrew Cask でインストールされ、かつPATHがそれを指しているかチェック
    if [[ "$OS_TYPE" == "macos" ]] && command -v brew &>/dev/null; then
        local brew_prefix
        brew_prefix=$(brew --prefix 2>/dev/null)
        # パスがbrew prefix配下の場合のみcaskチェック
        if [[ -n "$brew_prefix" ]] && [[ "$resolved_path" == "$brew_prefix"* || "$resolved_path" == "/Applications/"* ]]; then
            if brew list --cask 2>/dev/null | grep -q "^claude$"; then
                echo "homebrew-cask"
                return
            fi
        fi
    fi

    # フォールバック: claude update コマンドの存在で判定
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

    # パスを解決して実際のインストール元を特定（macOS/Linux対応）
    local resolved_path
    if command -v realpath &>/dev/null; then
        resolved_path=$(realpath "$codex_path" 2>/dev/null)
    elif command -v greadlink &>/dev/null; then
        resolved_path=$(greadlink -f "$codex_path" 2>/dev/null)
    elif [[ -L "$codex_path" ]]; then
        # macOS標準readlink（-fなし）でシンボリックリンクのターゲットを取得
        local link_target
        link_target=$(readlink "$codex_path" 2>/dev/null)
        # 相対パスの場合はdirname を使って絶対パスに変換
        if [[ "$link_target" != /* ]]; then
            resolved_path="$(cd "$(dirname "$codex_path")" && cd "$(dirname "$link_target")" && pwd)/$(basename "$link_target")"
        else
            resolved_path="$link_target"
        fi
    else
        resolved_path="$codex_path"
    fi

    # パスベースで判定（npm vs brew）
    if [[ "$resolved_path" == *"node_modules"* ]] || [[ "$codex_path" == *".nvm/"* ]] || [[ "$codex_path" == *".npm/"* ]] || [[ "$codex_path" == */fnm/* ]] || [[ "$resolved_path" == */fnm/* ]]; then
        echo "npm"
        return
    fi

    # macOS: brew prefix を確認
    if [[ "$OS_TYPE" == "macos" ]] && command -v brew &>/dev/null; then
        local brew_prefix
        brew_prefix=$(brew --prefix 2>/dev/null)
        if [[ -n "$brew_prefix" ]] && [[ "$resolved_path" == "$brew_prefix"* ]]; then
            echo "brew"
            return
        fi
    fi

    # フォールバック: npm list でチェック
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

    # パスを解決して実際のインストール元を特定（macOS/Linux対応）
    local resolved_path
    if command -v realpath &>/dev/null; then
        resolved_path=$(realpath "$opencode_path" 2>/dev/null)
    elif command -v greadlink &>/dev/null; then
        resolved_path=$(greadlink -f "$opencode_path" 2>/dev/null)
    elif [[ -L "$opencode_path" ]]; then
        # macOS標準readlink（-fなし）でシンボリックリンクのターゲットを取得
        local link_target
        link_target=$(readlink "$opencode_path" 2>/dev/null)
        # 相対パスの場合はdirname を使って絶対パスに変換
        if [[ "$link_target" != /* ]]; then
            resolved_path="$(cd "$(dirname "$opencode_path")" && cd "$(dirname "$link_target")" && pwd)/$(basename "$link_target")"
        else
            resolved_path="$link_target"
        fi
    else
        resolved_path="$opencode_path"
    fi

    # パスベースで判定（npm vs brew）
    if [[ "$resolved_path" == *"node_modules"* ]] || [[ "$opencode_path" == *".nvm/"* ]] || [[ "$opencode_path" == *".npm/"* ]] || [[ "$opencode_path" == */fnm/* ]] || [[ "$resolved_path" == */fnm/* ]]; then
        echo "npm"
        return
    fi

    # macOS: brew prefix を確認（どちらのformula名か特定）
    if [[ "$OS_TYPE" == "macos" ]] && command -v brew &>/dev/null; then
        local brew_prefix
        brew_prefix=$(brew --prefix 2>/dev/null)
        if [[ -n "$brew_prefix" ]] && [[ "$resolved_path" == "$brew_prefix"* ]]; then
            # brewからインストールされている場合、formula名を特定
            if brew list opencode &>/dev/null 2>&1; then
                echo "brew:opencode"
                return
            elif brew list opencode-ai &>/dev/null 2>&1; then
                echo "brew:opencode-ai"
                return
            fi
        fi
    fi

    # フォールバック: npm list でチェック
    if command -v npm &>/dev/null && npm list -g opencode-ai &>/dev/null 2>&1; then
        echo "npm"
        return
    fi

    echo "unknown"
}

# バージョン表示モード
show_versions() {
    echo "Environment: $OS_TYPE"
    echo "Claude Code: $(get_claude_version)"
    echo "Codex CLI:   $(get_codex_version)"
    echo "opencode:    $(get_opencode_version)"
}

# メイン処理
main() {
    # --version オプション
    if [[ "$1" == "--version" ]] || [[ "$1" == "-v" ]]; then
        show_versions
        exit 0
    fi

    echo "=== Claude Code, Codex CLI & opencode Update ==="
    echo "Environment: $OS_TYPE"
    echo ""

    # インストール方法の検出
    local claude_install codex_install opencode_install
    claude_install=$(detect_claude_install)
    codex_install=$(detect_codex_install)
    opencode_install=$(detect_opencode_install)

    # 検出失敗時のエラー処理
    if [[ "$claude_install" == "not_found" ]]; then
        echo "Error: Claude Code is not installed"
        exit 1
    fi
    if [[ "$codex_install" == "not_found" ]]; then
        echo "Error: Codex CLI is not installed"
        exit 1
    fi
    if [[ "$codex_install" == "unknown" ]]; then
        echo "Error: Could not detect Codex CLI installation method"
        exit 1
    fi
    if [[ "$opencode_install" == "not_found" ]]; then
        echo "Warning: opencode is not installed (skipping)"
        opencode_install="skip"
    fi
    if [[ "$opencode_install" == "unknown" ]]; then
        echo "Warning: Could not detect opencode installation method (skipping)"
        opencode_install="skip"
    fi

    # 更新前バージョン取得
    local claude_before codex_before opencode_before
    claude_before=$(get_claude_version)
    codex_before=$(get_codex_version)
    opencode_before=$(get_opencode_version)

    echo "[Before]"
    echo "claude:   $claude_before ($claude_install)"
    echo "codex:    $codex_before ($codex_install)"
    echo "opencode: $opencode_before ($opencode_install)"
    echo ""

    # Claude Code アップデート
    echo -n "Updating Claude Code ($claude_install)... "
    case "$claude_install" in
        native)
            if claude update </dev/null; then
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

    # Codex CLI アップデート
    echo -n "Updating Codex CLI ($codex_install)... "
    case "$codex_install" in
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

    # opencode アップデート
    if [[ "$opencode_install" != "skip" ]]; then
        echo -n "Updating opencode ($opencode_install)... "
        case "$opencode_install" in
            npm)
                # npm update を実行し、stderrをキャプチャ
                local update_output
                local update_exit
                update_output=$(npm update -g opencode-ai 2>&1)
                update_exit=$?

                if [[ $update_exit -eq 0 ]]; then
                    echo "✓"
                elif grep -qF -- "Could not find package" <<<"$update_output"; then
                    # プラットフォーム固有パッケージ解決エラーの場合のみフォールバック
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
    fi

    echo ""

    # 更新後バージョン取得
    local claude_after codex_after opencode_after
    claude_after=$(get_claude_version)
    codex_after=$(get_codex_version)
    opencode_after=$(get_opencode_version)

    echo "[After]"
    echo "claude:   $claude_after"
    echo "codex:    $codex_after"
    echo "opencode: $opencode_after"
    echo ""

    # 結果サマリー
    if [[ ${#ERRORS[@]} -eq 0 ]]; then
        echo "✓ Update completed"
    else
        echo "⚠ Errors occurred:"
        for err in "${ERRORS[@]}"; do
            echo "  - $err"
        done
        exit 1
    fi
}

main "$@"
