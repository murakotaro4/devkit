# 環境と任意適用

必要な節を環境判定または承認対象の適用直前に読む。

## 環境前提チェック

`command -v` で `claude` / `codex` / `cursor-agent` / `node` / `uv` を確認し、OK / MISSING と影響を報告する。
インストール自体は行わない。

| MISSING | 影響 |
|---|---|
| `uv` | 必須同期と Windows font を実行できないため、同期前に停止。macOS は `brew install uv`、Windows は `winget install --id astral-sh.uv` |
| `node` | statusline だけ skip。他の同期と font は継続。必要なら `brew install node` |
| `claude` | goal-prompt の `/goal` 実行環境がない。同期は継続 |
| `codex` | Claude 親・判定不能の dig CLI backend が使えない。Codex 親の実装・子レビューには不要。同期は継続 |
| `cursor-agent` | Claude 親・判定不能の dig 実装 lane が使えない。Codex 親の実装には不要。同期は継続 |

## statusline 適用

Claude 親かつ `node` がある場合だけ対象。check と apply は別のシェル呼び出しになるため毎回 `SKILL_DIR` を代入する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
node "$SKILL_DIR/../../statusline/install.js" --check
```

差分を提示し、承認後に適用する。DevKit 管理済み / 未導入は `--check` を外す。他設定との競合は上書きを追加確認し、承認後だけ `--force` を末尾へ付ける。Codex 親・判定不能・node 不在は理由付き skip。

## ターミナルフォント適用(Windows のみ)

非 Windows は skip。Windows Terminal の UDEV Gothic NF を次のコマンドで確認し、選択肢付き質問で承認後、同じコマンドから `--check` だけ外して適用する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/setup_terminal_font.py" --check --format json
```

ダウンロード失敗、SHA-256 不一致、font 未登録、Windows Terminal 未検出は案内のみで setup 全体を止めない。font 未検出時は settings.json を書かない。
