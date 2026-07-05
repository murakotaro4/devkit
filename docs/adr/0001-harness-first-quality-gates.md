# ADR 0001: Harness-First Quality Gates

## Status

Accepted

2026-07-05 注記: 本 ADR の判断は実施済み。`amazon-search`（browser DOM 上で eval する JavaScript を含む skill）は削除済みで、v6/v7 の配布面に browser 実行の JavaScript を持つ skill は存在しない。以下の Decision / Consequences は決定当時の記述として保持する。なお v7 同梱の statusline は Node 実装であり、browser eval を対象とした本方針の例外条項には該当しない。

## Context

DevKit は複数 runtime へ配布する workflow / skill の母体であり、品質をプロンプト運用だけに依存させると再現性が落ちる。
特に hook、review gate、repo 整合チェックのような再利用される仕組みは、文章によるお願いよりも決定論的なツールで強制した方が安定する。

この repo には Python、PowerShell、Markdown、YAML、JSON が混在し、workflow hook と repo チェックは将来のメンテナが理解しやすい単一の実行入口が必要だった。

## Decision

- Harness の標準実行入口は `uv` と Python に統一する
- repo 整合チェックと workflow hook は Python 実装へ寄せる
- ローカル/CI の品質ゲートは `uv run` から起動する
- `AGENTS.md` / README には、prose より決定論的ツールを優先する原則を明記する
- 例外的に browser 上で動く JavaScript を持つ skill は中核方針から外す

## Consequences

- hook / CI / pre-commit の入口が統一され、保守対象が絞られる
- Python ベースで lint / format / validation をまとめやすくなる
- repo 固有の Node スクリプトは段階的に削減できる
- browser DOM 上で eval する JavaScript を含む skill は Harness 方針を濁すため、今回 `amazon-search` を削除する
