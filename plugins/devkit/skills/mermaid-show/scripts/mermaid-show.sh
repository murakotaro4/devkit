#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
mermaid-show.sh - Mermaid（.mmd / Markdown内```mermaid）をPNG化して表示する

Usage:
  mermaid-show.sh [--id <anchor>] [--index <n>] [--open] <path(.md|.mmd)>

Options:
  --id <anchor>    Markdown内の <a id="..."></a> を起点に直後の最初の```mermaidを表示
  --index <n>      Markdown内のn番目（1始まり）の```mermaidを表示
  --open           生成したPNGを open(mac) / xdg-open(linux) で開く
  -h, --help       ヘルプ表示

Output:
  /tmp/mermaid-show/<timestamp-pid>/diagram.mmd
  /tmp/mermaid-show/<timestamp-pid>/diagram.png
EOF
}

err() {
  echo "error: $*" >&2
  exit 1
}

warn() {
  echo "WARN: $*" >&2
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || err "$1 が見つかりません"
}

is_mermaid_fence_start() {
  [[ "$1" =~ ^\`\`\`[[:space:]]*mermaid[[:space:]]*$ ]]
}

is_fence_end() {
  [[ "$1" =~ ^\`\`\`[[:space:]]*$ ]]
}

MD_BLOCK_COUNT=0
MD_BLOCK_ANCHORS=()

scan_md_info() {
  local md_path="$1"
  local in_mermaid=0
  local pending_anchor=""
  local line=""

  MD_BLOCK_COUNT=0
  MD_BLOCK_ANCHORS=()

  while IFS= read -r line || [ -n "$line" ]; do
    if [ "$in_mermaid" -eq 0 ]; then
      if [[ "$line" =~ \<a[[:space:]]+id=\"([^\"]+)\" ]]; then
        pending_anchor="${BASH_REMATCH[1]}"
      fi

      if is_mermaid_fence_start "$line"; then
        MD_BLOCK_COUNT=$((MD_BLOCK_COUNT + 1))
        if [ -n "$pending_anchor" ]; then
          MD_BLOCK_ANCHORS[$MD_BLOCK_COUNT]="$pending_anchor"
          pending_anchor=""
        fi
        in_mermaid=1
      fi
    else
      if is_fence_end "$line"; then
        in_mermaid=0
      fi
    fi
  done <"$md_path"
}

print_md_hints() {
  local md_path="$1"
  local i=0

  echo "INFO: Mermaid blocks detected: $MD_BLOCK_COUNT" >&2
  if [ "$MD_BLOCK_COUNT" -gt 1 ]; then
    echo "INFO: ヒント: --index 2 のように指定できます。" >&2
  fi

  # 推測できた anchor -> index を出す（無ければスキップ）
  for ((i = 1; i <= MD_BLOCK_COUNT; i++)); do
    if [ -n "${MD_BLOCK_ANCHORS[$i]:-}" ]; then
      echo "INFO: anchor: ${MD_BLOCK_ANCHORS[$i]} -> --index $i" >&2
    fi
  done
}

extract_by_index() {
  local md_path="$1"
  local target_index="$2"
  local out_mmd="$3"
  local in_mermaid=0
  local idx=0
  local line=""
  local wrote_any=0

  : >"$out_mmd"

  while IFS= read -r line || [ -n "$line" ]; do
    if [ "$in_mermaid" -eq 0 ]; then
      if is_mermaid_fence_start "$line"; then
        idx=$((idx + 1))
        in_mermaid=1
      fi
      continue
    fi

    if is_fence_end "$line"; then
      if [ "$idx" -eq "$target_index" ]; then
        break
      fi
      in_mermaid=0
      continue
    fi

    if [ "$idx" -eq "$target_index" ]; then
      printf '%s\n' "$line" >>"$out_mmd"
      wrote_any=1
    fi
  done <"$md_path"

  if [ "$wrote_any" -ne 1 ]; then
    err "Markdownから mermaid ブロック（--index $target_index）を抽出できませんでした: $md_path"
  fi
}

extract_after_anchor() {
  local md_path="$1"
  local target_id="$2"
  local out_mmd="$3"
  local found_anchor=0
  local in_mermaid=0
  local wrote_any=0
  local line=""

  : >"$out_mmd"

  while IFS= read -r line || [ -n "$line" ]; do
    if [ "$found_anchor" -eq 0 ]; then
      if [[ "$line" =~ \<a[[:space:]]+id=\"([^\"]+)\" ]]; then
        if [ "${BASH_REMATCH[1]}" = "$target_id" ]; then
          found_anchor=1
        fi
      fi
      continue
    fi

    if [ "$in_mermaid" -eq 0 ]; then
      if is_mermaid_fence_start "$line"; then
        in_mermaid=1
      fi
      continue
    fi

    if is_fence_end "$line"; then
      break
    fi

    printf '%s\n' "$line" >>"$out_mmd"
    wrote_any=1
  done <"$md_path"

  if [ "$found_anchor" -ne 1 ]; then
    err "Markdown内に <a id=\"$target_id\"></a> が見つかりませんでした: $md_path"
  fi
  if [ "$wrote_any" -ne 1 ]; then
    err "<a id=\"$target_id\"></a> の後に mermaid ブロックが見つかりませんでした: $md_path"
  fi
}

open_file() {
  local path="$1"
  if command -v open >/dev/null 2>&1; then
    open "$path" >/dev/null 2>&1 || warn "open に失敗しました: $path"
    return
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$path" >/dev/null 2>&1 || warn "xdg-open に失敗しました: $path"
    return
  fi
  warn "open/xdg-open が見つからないため自動オープンできません: $path"
}

ANCHOR_ID=""
INDEX=""
OPEN=0
INPUT_PATH=""

while [ $# -gt 0 ]; do
  case "$1" in
    --id)
      [ $# -ge 2 ] || err "--id には値が必要です"
      ANCHOR_ID="$2"
      shift 2
      ;;
    --index)
      [ $# -ge 2 ] || err "--index には値が必要です"
      INDEX="$2"
      shift 2
      ;;
    --open)
      OPEN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      err "未知のオプション: $1"
      ;;
    *)
      if [ -n "$INPUT_PATH" ]; then
        err "入力パスは1つだけ指定してください（重複: $1）"
      fi
      INPUT_PATH="$1"
      shift
      ;;
  esac
done

if [ -z "$INPUT_PATH" ]; then
  usage >&2
  err "入力パスが必要です（.md または .mmd）"
fi

if [ -n "$ANCHOR_ID" ] && [ -n "$INDEX" ]; then
  err "--id と --index は同時指定できません"
fi

if [ -n "$INDEX" ]; then
  [[ "$INDEX" =~ ^[0-9]+$ ]] || err "--index は正の整数で指定してください: $INDEX"
  [ "$INDEX" -ge 1 ] || err "--index は 1 以上で指定してください: $INDEX"
fi

if [ ! -f "$INPUT_PATH" ]; then
  err "ファイルが見つかりません: $INPUT_PATH"
fi

require_cmd node
require_cmd npx
require_cmd kitten

ext="${INPUT_PATH##*.}"
ext="$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')"

OUT_ROOT="${OUT_ROOT:-/tmp/mermaid-show}"
RUN_ID="$(date +%Y%m%d_%H%M%S)-$$"
OUT_DIR="$OUT_ROOT/$RUN_ID"
mkdir -p "$OUT_DIR"

WORK_MMD="$OUT_DIR/diagram.mmd"
OUT_PNG="$OUT_DIR/diagram.png"

DEFAULTED_INDEX=0

case "$ext" in
  mmd)
    cp "$INPUT_PATH" "$WORK_MMD"
    ;;
  md|markdown)
    scan_md_info "$INPUT_PATH"
    if [ -z "$ANCHOR_ID" ] && [ -z "$INDEX" ]; then
      INDEX="1"
      DEFAULTED_INDEX=1
    fi

    if [ "$DEFAULTED_INDEX" -eq 1 ]; then
      echo "INFO: --id/--index 未指定のため、1枚目（--index 1）を表示します。" >&2
      print_md_hints "$INPUT_PATH"
    fi

    if [ -n "$ANCHOR_ID" ]; then
      extract_after_anchor "$INPUT_PATH" "$ANCHOR_ID" "$WORK_MMD"
    else
      if [ "$MD_BLOCK_COUNT" -eq 0 ]; then
        err "Markdown内に mermaid ブロック（コードフェンス: mermaid）が見つかりませんでした: $INPUT_PATH"
      fi
      if [ "$INDEX" -gt "$MD_BLOCK_COUNT" ]; then
        err "--index $INDEX は範囲外です（1..$MD_BLOCK_COUNT）: $INPUT_PATH"
      fi
      extract_by_index "$INPUT_PATH" "$INDEX" "$WORK_MMD"
    fi
    ;;
  *)
    err "未対応の拡張子です（.md/.markdown/.mmd のみ）: $INPUT_PATH"
    ;;
esac

npx -y --package @mermaid-js/mermaid-cli mmdc -i "$WORK_MMD" -o "$OUT_PNG"

shown=0
if kitten icat "$OUT_PNG"; then
  shown=1
else
  warn "kitten icat が失敗しました（非TTY等の可能性）。"
fi

if [ "$OPEN" -eq 1 ]; then
  open_file "$OUT_PNG"
fi

echo "MMD: $WORK_MMD"
echo "PNG: $OUT_PNG"
