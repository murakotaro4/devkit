---
name: "discord-rust-server-ops"
description: "DiscordのRust（ゲーム）カテゴリ運用を自動化する。『Rustカテゴリにチャンネルを追加したい』『作成済みチャンネルの権限/トピックを調整したい』『kuro-rust-channel-botでdry-run→apply→検証したい』依頼で使う。personal-opsの `scripts/discord_create_channels.py` と `configs/discord/*.json` を前提に実行する。"
allowed-tools: ["Bash", "Read", "Grep", "Glob"]
---

# /discord-rust-server-ops - Rustカテゴリ運用

## トピック
$ARGUMENTS

## 目的
- Discordの `Rust` カテゴリ配下を、安全に再現可能な手順で作成/更新する。
- Bot APIで `dry-run -> apply -> verify` を固定化し、誤操作を防ぐ。
- 設定変更後の運用メモ更新まで一連で実施する。

## 前提
- 作業ディレクトリは `personal-ops` リポジトリ。
- 必須ファイル:
  - `scripts/discord_create_channels.py`
  - `configs/discord/*.json`
  - `.env.discord`（`DISCORD_BOT_TOKEN` 含む）
- 秘密情報は表示しない（トークン値を出力しない）。

## 標準フロー
1. 事前確認を実行する。
```bash
[ -f .env.discord ] && echo "env_exists" || echo "env_missing"
awk -F= '/^DISCORD_BOT_TOKEN=/{print "DISCORD_BOT_TOKEN=" (length($2)>0?"set":"empty")} /^DISCORD_GUILD_ID=/{print "DISCORD_GUILD_ID=" (length($2)>0?"set":"empty")} /^DISCORD_CATEGORY_ID=/{print "DISCORD_CATEGORY_ID=" (length($2)>0?"set":"empty")}' .env.discord
uv run python scripts/discord_create_channels.py --help
```

2. `DISCORD_GUILD_ID` / `DISCORD_CATEGORY_ID` が未設定ならAPIで特定する。
```bash
uv run python - <<'PY'
import json, os, urllib.request
from pathlib import Path
for line in Path(".env.discord").read_text(encoding="utf-8").splitlines():
    s=line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k,v=s.split("=",1)
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
token=os.getenv("DISCORD_BOT_TOKEN","").strip()
req=urllib.request.Request(
    "https://discord.com/api/v10/users/@me/guilds",
    headers={"Authorization":f"Bot {token}", "User-Agent":"discord-rust-skill/1.0"},
)
with urllib.request.urlopen(req, timeout=30) as r:
    guilds=json.loads(r.read().decode("utf-8"))
for g in guilds:
    print(g["id"], g["name"], sep="\t")
PY
```

3. 設定JSONを編集する（既定: `configs/discord/rust-minimal8.json`）。
   - 現行スクリプトで対応済み:
     - `name`
     - `type` (`text` / `voice`)
     - `read_only`（textのみ）
     - `topic`（textのみ）
   - 未対応設定（必要ならスクリプト拡張）:
     - slowmode
     - voice bitrate/user limit
     - きめ細かい権限上書き

4. `dry-run` を必ず実行する。
```bash
uv run python scripts/discord_create_channels.py \
  --env-file .env.discord \
  --spec configs/discord/rust-minimal8.json \
  --dry-run
```

5. 問題なければ `--apply` を実行する。
```bash
uv run python scripts/discord_create_channels.py \
  --env-file .env.discord \
  --spec configs/discord/rust-minimal8.json \
  --apply
```

6. 実行後に再度 `dry-run` し、`create=0` を確認する（冪等性確認）。

7. 運用記録を更新する。
   - `02_projects/streaming/discord-rust-server-ops.md`
   - 必要ならDM文面ファイル（`02_projects/streaming/kuro-*.txt`）

## Bot導入/権限運用
- 招待URL（最小権限）:
  - `https://discord.com/oauth2/authorize?client_id=<CLIENT_ID>&scope=bot&permissions=1040`
- 一時的に人間へ強い権限を付与して導入した場合、導入後は外す。
- 恒久運用はBot専用ロール（`View Channels` + `Manage Channels`）を推奨する。

## 禁止事項
- `.env.discord` の値を会話に出さない。
- `agent-browser snapshot` の個人情報を貼り付けない。
- 既存カテゴリ/チャンネルの破壊的変更を勝手に行わない。
