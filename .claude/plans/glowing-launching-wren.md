# improve-skill のデフォルト動作を auto-retro に変更

## Context

`improve-skill` はセッション中のエラーやユーザーフィードバックを検出してスキル改善を提案するが、現状は `--auto-retro` フラグを明示的に渡さないと発動しない。dig adapter からの呼び出しも欠落しており、実質的に使われていない。

**修正方針**: `improve-skill` を呼んだらデフォルトで auto-retro が走るようにする。`--auto-retro` フラグは不要にし、`refresh` / `create` は明示的に指定した時だけ動く。

## 根本原因

1. `improve-skill` のモード判定が `--auto-retro` フラグ依存 → 呼び出し側が忘れると発動しない
2. dig-claude / dig-codex adapter に呼び出し自体がない
3. dig-core のトリガー条件が「エラー時のみ」で厳しすぎる
4. Step 0 がエラー/リトライのみ検出し、ユーザーフィードバックを見ていない

## 修正内容

### 1. improve-skill SKILL.md のモード判定をデフォルト auto-retro に変更

**ファイル**: `plugins/devkit/skills/improve-skill/SKILL.md`

#### モード判定 (L22-24) を変更

変更前:
```
- `$ARGUMENTS` に `--auto-retro` を含む → `auto-retro` モード
- それ以外 → AskUserQuestion で `refresh` / `create` を確定
```

変更後:
```
- `$ARGUMENTS` に `--refresh` を含む → `refresh` モード
- `$ARGUMENTS` に `--create` を含む → `create` モード
- それ以外（引数なし含む）→ `auto-retro` モード（デフォルト）
```

`--auto-retro` フラグは廃止。後方互換は不要。

#### 目的セクション (L17-18) を更新

変更前: `auto-retro: $ARGUMENTS に --auto-retro を含む場合に起動`
変更後: `auto-retro: デフォルト動作。引数なしまたは --auto-retro で起動`

#### 1 セッション 1 回制約 (L43) を維持

既存の `1セッション1回制約: 既に実行済みなら「振り返り済み」と報告してスキップ` をそのまま維持。これにより多重実行を防止する。

#### auto-retro 実行ルール (L40-47) に Plan モード制御を追加

以下のルールを追加:
```
- Plan モード中（dig-codex 等）の場合、Step 3（編集適用・Codex レビュー・コミット）は実行せず、修正提案の提示のみ行う。Step 0-2 は通常通り実行する。
```

これにより dig-codex から呼び出された場合も副作用（ファイル編集・コミット）が発生しない。

#### L97-98 のトリガー説明を更新

変更前: `他スキルの最終ステップから --auto-retro 引数付きで自動トリガーされる`
変更後: `他スキルの最終ステップから自動トリガーされる（引数なしでデフォルト動作）`

#### Step 0 (L100-109) にユーザーフィードバック検出を追加

現在の検出対象（エラー/リトライ）に加えて:
- ユーザーが手順や方針を修正・却下した（「それは違う」「こうして」等）
- ユーザーがスキルの出力に不満を示した（「いらない」「多すぎる」等）
- ユーザーがワークフローの進め方について指摘した

#### L44 の検出結果判定条件を更新

変更前: `エラー検出結果が0件なら「振り返り不要」と報告してスキップ`
変更後: `エラーおよびユーザーフィードバックの検出結果が0件なら「振り返り不要」と報告してスキップ`

#### L46 の修正対象条件を更新

変更前: `修正対象は**エラーが発生したスキルの SKILL.md / CLAUDE.md のみ**`
変更後: `修正対象は**エラーが発生した、またはユーザーフィードバックが関連するスキルの SKILL.md / CLAUDE.md のみ**`

### 2. dig-core SKILL.md のトリガー条件を緩和 + 呼び出しを簡略化

**ファイル**: `plugins/devkit/skills/dig-core/SKILL.md` (L156-162)

変更前:
```
> 実行フェーズでエラーやリトライが発生した場合のみ実行する。
> エラーがなければ「振り返り不要」と報告してスキップする。

`devkit:improve-skill --auto-retro` を実行。
```

変更後:
```
> セッション完了時に毎回実行する。
> エラー・リトライ・ユーザーからの修正指摘があった場合は修正提案を行う。
> 改善点がなければ「振り返り不要」と報告してスキップする。

`devkit:improve-skill` を実行。
```

### 3. dig-claude SKILL.md に呼び出しを追記

**ファイル**: `plugins/devkit/skills/dig-claude/SKILL.md`

Phase 8 セクション (L224-240) の後に追記:
```markdown
### セッション振り返り（Phase 8 完了後）

Phase 8 完了後に `devkit:improve-skill` を実行する。
dig-core 契約の「セッション振り返り」に従う。
```

### 4. dig-codex SKILL.md にも呼び出しを追記

**ファイル**: `plugins/devkit/skills/dig-codex/SKILL.md`

dig-codex は計画フェーズのみだが、計画完了（REVIEW_GATE_PLAN 通過 + DONE 遷移）後にセッション振り返りを実行する。ただし dig-codex は Plan モード中のため、auto-retro の Step 3（編集・コミット）は実行せず、**修正提案の提示のみ**にとどめる。L225 の DONE 遷移の後に追記:
```markdown
### セッション振り返り（計画完了後）

計画完了後に `devkit:improve-skill` を実行する。
dig-core 契約の「セッション振り返り」に従う。
ただし dig-codex は計画専用のため、Step 3（編集・コミット）は実行せず修正提案の提示のみ。
```

### 5. version bump

**ファイル**: `plugins/devkit/.claude-plugin/plugin.json`

`2.3.0` → `3.0.0`（breaking change: improve-skill のデフォルト動作が auto-retro に変更、`--auto-retro` フラグ廃止）

## 対象ファイル

- `plugins/devkit/skills/improve-skill/SKILL.md` — モード判定変更 + Step 0 拡張 + 修正対象条件更新
- `plugins/devkit/skills/improve-skill/references/question-flow.md` — デフォルト auto-retro への変更を反映
- `plugins/devkit/skills/dig-core/SKILL.md` — トリガー条件緩和 + 呼び出し簡略化
- `plugins/devkit/skills/dig-claude/SKILL.md` — セッション振り返りセクション追記
- `plugins/devkit/skills/dig-codex/SKILL.md` — セッション振り返りセクション追記
- `plugins/devkit/.claude-plugin/plugin.json` — version bump

## 検証方法

1. `uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-fast` が通ること
2. improve-skill SKILL.md: 引数なしで auto-retro がデフォルトになっていること（grep 確認）
3. improve-skill SKILL.md: Step 0 にユーザーフィードバック検出が含まれること
4. dig-claude SKILL.md: `devkit:improve-skill` の呼び出しがあること
5. dig-core SKILL.md: `--auto-retro` フラグなしの `devkit:improve-skill` 呼び出しになっていること
6. dig-codex SKILL.md: セッション振り返りセクションがあること
7. `--auto-retro` の全参照箇所（dig-core L162, improve-skill L18,23,42,97,98）が更新・廃止されていること
