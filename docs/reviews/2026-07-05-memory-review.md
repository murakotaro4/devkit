# memory-review: devkit repo 全体 + auto-memory + Codex メモリ（2026-07-05）

監査範囲: repo 全体 + Claude auto-memory（`~/.claude/projects/-Users-murakotaro-repos-devkit/memory/`、git 管理外）+ Codex メモリ（`~/.codex/memories/MEMORY.md`、`~/.codex/AGENTS.md`、git 管理外）。read-only 監査を 3 並列サブエージェント（docs 整合 / スキル契約 / 安全性・repo 外メモリ）で実施。

## 1. 結論（3件以内）

1. **危険な自動化が 1 件**: improve-skill の retro が、修正内容の承認だけで「全ファイルステージング → 自動 commit」まで実行する契約になっており、他 4 スキルと AGENTS.md の「commit はユーザー指示時のみ」と矛盾している（`plugins/devkit/skills/improve-skill/SKILL.md:154-161`）。
2. **共通契約のコピー&ドリフトが進行中**: ハーネス判定キー（4 通り）、codex exec 実行形（モデル指定が 3 箇所で食い違い）、タスクリスト連動、dig 引き継ぎ形式が各 SKILL.md に逐語コピーされ、片方だけ更新される事故が既に起きている。
3. **カバレッジの最大の空白はリリース工程**（当初分析）。ただし demand-pull 基準の再検討により、release 含む新スキル追加はすべて見送りと判断（セクション末尾の付記参照）。

## 2. 全体評価

| 観点 | 評価 | 根拠 |
|------|------|------|
| 最新性 | ○（軽微な古さのみ） | スキル面 5 本・version 7.1.0 は README / AGENTS.md / plugin.json / marketplace で完全一致。古さは auto-memory の解決済み残課題と ADR の時制程度 |
| 一貫性 | △ | codex exec モデル指定・ハーネス判定キー・`request_user_input` の扱いがスキル間で食い違う |
| 安全性 | △ | 秘密情報転記なし・破壊的自動化ほぼなし。ただし improve-skill retro の自動 commit が承認ゲート外 |
| 参照しやすさ | ○ | AGENTS.md 正本 + CLAUDE.md 参照入口の設計は機能。wiki-link も全て実在 |
| CLAUDE.md 肥大化リスク | ○（低） | 参照入口に徹している。ただし `.claude-plugin/CLAUDE.md`（claude-mem 自動生成）が同名で追跡され紛らわしい |
| AI 勝手判断リスク | △ | improve-skill の codex exec 実行形が未定義（`< /dev/null` 等の焼き込み漏れ）で即興補完の余地 |

## 3. 重要な問題点

| 問題 | 該当箇所 | なぜ問題か | 推奨対応 | 自動修正可否 | 人間確認要否 |
|------|----------|------------|----------|--------------|--------------|
| retro の自動 commit | `plugins/devkit/skills/improve-skill/SKILL.md:154-161` | 修正承認と commit 承認は別物。「全ファイルステージング」は無関係な変更も巻き込む。他スキル・AGENTS.md と矛盾 | commit を明示承認ゲートの後ろへ。ステージングは編集対象ファイルに限定 | 可（契約変更なので minor bump） | 要 |
| codex exec モデル指定の矛盾 | `AGENTS.md:79` vs `dig/SKILL.md:87` vs `templates/codex/config.shared.toml:5` | dig は「`-m` を焼き込まない」原則なのに AGENTS.md が `-m gpt-5.3-codex-spark` をハードコード。config 既定は gpt-5.4 | AGENTS.md からモデル指定を外し「config 既定に従う」へ統一 | 可 | 要 |
| ハーネス判定キーが 4 通り | `dig/SKILL.md:20-22` / `refactor` / `memory-review` / `setup` 各 20-22 行付近 | 同じ契約が 5 コピーされ判定信号が食い違う。`request_user_input` の信頼性評価も 3 段階に分裂 | 判定ロジックを 1 箇所に正本化し参照させる | 可（横断変更） | 要 |
| improve-skill の codex exec 実行形未定義 | `improve-skill/SKILL.md:158` | 「CLAUDE.mdルール準拠」と実在しない参照先を指し、`< /dev/null` / `-a never` の焼き込みなし。stdin ハング再発リスク | 参照を AGENTS.md へ修正し具体コマンド例を追記 | 可 | 不要 |
| version-gate ロジック 2 実装 | `devkit_harness.py:260-311` と `check_plugin_version_bump.py:103-154` | 同じ判定が 2 箇所にあり docs は片方しか説明しない。片方だけ改修で乖離 | 一本化するか二段構成を docs に明記 | 可 | 要 |

## 4. 分類結果

| 分類 | 項目 | 根拠 | 影響度 |
|------|------|------|--------|
| update | improve-skill retro の commit ゲート追加 | `improve-skill/SKILL.md:154-161` | 高 |
| update | AGENTS.md 相談ルールのモデル指定除去 | `AGENTS.md:79` | 中 |
| update | improve-skill の codex exec 実行形・参照先修正 | `improve-skill/SKILL.md:158` | 中 |
| update | auto-memory 索引の「未対応フォローアップ」表記（prek / branch protection は解決済み） | `memory/MEMORY.md:4` | 中 |
| update | auto-memory の「本機 statusline 適用」残課題（適用済み） | `memory/devkit-v7-statusline-setup-refactor.md:20` | 中 |
| update | `.githooks/pre-commit` の `cargo install prek` 案内（実運用は `uv tool install prek`） | `.githooks/pre-commit:8` | 低 |
| update | README Migration Notice に `amazon-search` 追記 | `README.md:8`（prune 実装 `devkit-lib.sh:276` は認識済み） | 低 |
| update | AGENTS.md Key Paths の templates 記述（rules テンプレートが欠落） | `AGENTS.md:46` | 低 |
| update | version gate の文言「同じなら block」→「以下なら block」 | `AGENTS.md:68`, `README.md:200`（実装は `check_plugin_version_bump.py:154` で `<=`） | 低 |
| update | ADR 0001 の時制固定（amazon-search「今回削除」・browser JS 例外） | `docs/adr/0001-harness-first-quality-gates.md:20-27` | 低 |
| merge | ハーネス判定・タスクリスト連動・codex exec 実行形の正本化 | 5 SKILL.md 横断 | 中 |
| merge | Release Rules の正本を AGENTS.md に定め README は参照に縮約 | `AGENTS.md:63-73` / `README.md:195-205` | 中 |
| merge | BOM チェック二重実装の一本化 | `.github/workflows/check-bom.yml` vs `devkit_harness.py:315` | 低 |
| merge | dig 引き継ぎ形式の二重定義（現状整合、二重管理のみ） | `refactor/SKILL.md:114-134` / `memory-review/SKILL.md:217-237` | 低 |
| keep | codex exec stdin ルール（`< /dev/null`）— テストで強制済み | `test_document_consistency.py:111-117` | — |
| keep | cursor-agent `--force` 契約とメモリの一致 | `dig/SKILL.md:190` | — |
| keep | Windows 実機検証を残課題とするメモリ表記（正確） | `memory/devkit-v7-statusline-setup-refactor.md:20` | — |
| archive | Codex メモリの日次 marketplace upgrade 記述（v6 で撤回済み、履歴性あり） | `~/.codex/memories/MEMORY.md:99` | 低 |
| delete candidate | なし | — | — |
| needs human decision | Commit Rules の決定論的強制（commitlint 等）を入れるか、prose 許容を明記するか | `AGENTS.md:48-61` / `prek.toml` | 中 |
| needs human decision | `.claude-plugin/CLAUDE.md`（claude-mem 自動生成）を gitignore するか | `.claude-plugin/CLAUDE.md:1` | 低 |
| needs human decision | setup のルール書き込みに差分承認ゲートを入れるか（statusline は承認あり、非対称） | `setup/SKILL.md:43-56` | 低 |

## 5. 矛盾リスト

| ペア | A | B | 判断 |
|------|---|---|------|
| commit 方針 | `improve-skill/SKILL.md:161`（自動 commit） | `AGENTS.md:24` ほか 4 スキル（ユーザー指示時のみ） | improve-skill 側を修正 |
| codex モデル指定 | `AGENTS.md:79`（`-m gpt-5.3-codex-spark`） | `dig/SKILL.md:87`（`-m` 焼き込み禁止）+ `config.shared.toml:5`（gpt-5.4） | AGENTS.md 側を修正 |
| `request_user_input` の扱い | `dig/SKILL.md:18`（判定に使わない） | `setup/SKILL.md:21`（判定に使う） | 方針を一本化 |
| prek 導入手段 | `.githooks/pre-commit:8`（cargo） | 実機・メモリ（uv tool install） | フック文言を修正 |
| 削除スキル一覧 | `README.md:8`（amazon-search なし） | `devkit-lib.sh:276` / ADR（あり） | README に追記 |

## 6. 古い前提リスト

| 前提 | 根拠 | 現在の正本 | 推奨 |
|------|------|------------|------|
| prek 導入・branch protection が未対応 | `memory/MEMORY.md:4` | 実機に prek 導入済み・`devkit-dig-v5-rewrite.md:19,24` で解決済み | 索引行を更新 |
| 本機への statusline 適用が残課題 | `memory/devkit-v7-statusline-setup-refactor.md:20` | `~/.claude/settings.json` が適用済みパスを参照 | 残課題から除去（Windows 検証だけ残す） |
| Codex メモリの devkit 到達点が v6.1.0 | `~/.codex/memories/MEMORY.md:59,72` | repo v7.1.0 | 履歴のため削除不要。正本は repo と 1 行注記が候補 |
| browser JS スキルが存在し例外扱い | `docs/adr/0001:20-27` | v7 配布面は全て非ブラウザ | 時制を確定し注記 |

## 7. AI が勝手に決めると危険な点

### Known unknowns

- AGENTS.md の `-m gpt-5.3-codex-spark` が「相談は軽量モデルで安く」という意図的な固定なのか、単なる更新漏れなのか。
- version-gate 二重実装（harness inline + 独立スクリプト）のどちらを正本にするか。
- Commit Rules を hook で強制するか、prose 運用を明示的に許容するか。

### Unknown unknowns

- Codex 親でしか踏まないパス（`request_user_input` 判定分岐など）は実機検証の証跡がなく、判定キー統一の際に Codex 側で壊れても検出する check がない。
- Codex グローバルメモリ（504KB、追記型）が今後どのセッションでどう注入されるかは devkit repo 側から制御できない。

## 8. 修正案（文章レベル）

- `improve-skill/SKILL.md` Step 3: 「編集適用 → レビュー」までで停止し、「コミットはユーザーが明示した場合のみ。ステージングは編集対象ファイルに限定」へ変更。
- `AGENTS.md:79`: `-m gpt-5.3-codex-spark -c model_reasoning_effort="medium"` を外し「モデルは config 既定に従う（`-m` を焼き込まない）」へ。
- `improve-skill/SKILL.md:158`: 「CLAUDE.mdルール準拠」→「AGENTS.md の Codex Exec 相談ルール準拠」+ `codex -a never exec ... < /dev/null` の具体形を併記。
- auto-memory 2 ファイル: 解決済み項目を残課題から除去。
- `.githooks/pre-commit`: `cargo install prek` → `uv tool install prek`。
- `README.md:8` / `AGENTS.md:46,68` / `README.md:200` / ADR 0001: 上記表のとおり文言修正。

## 9. 推奨する配置

| 配置先 | 内容 | 理由 |
|--------|------|------|
| AGENTS.md | ハーネス判定・タスクリスト連動・codex exec 実行形の「共通契約」節を新設（各 SKILL.md は参照） | 5 コピーのドリフトを止める唯一の構造的対策 |
| AGENTS.md | Release Rules の正本宣言（README は要点 + 参照） | 正本未指定の重複解消 |
| AGENTS.md | スキル採用基準（demand-pull・梯子・5 テスト）の明文化 | 場当たりなスキル増殖の防止（付記参照） |
| memory files (auto-memory) | 解決済み残課題の更新 | 次セッションの誤誘導防止 |

## 10. 次アクション（3つ以内）

1. 軽微修正（単一ファイル完結の 7 件: auto-memory 2 件 + `.githooks` + README/AGENTS.md/ADR 文言）を適用する。
2. 構造的修正（improve-skill の commit ゲート、共通契約の正本化、version-gate/BOM 一本化）を適用する。
3. スキル採用基準を AGENTS.md + improve-skill create モードに恒久化する（新スキル追加はなし）。

---

## 付記: 新スキル候補の判定記録（demand-pull 基準）

監査時のカバレッジギャップ分析では release / review / debug / test-gap が空白工程として挙がったが、「工程の空白を埋める」（gap-push）判断は場当たりなスキル増殖を招くため、採用判断を demand-pull 基準（証拠テスト → 最小手段の梯子 → 5 テスト）へ転換した（codex exec 相談で妥当性確認済み。監査可能性・撤退性の 2 軸は codex 提案を採用）。

- **release**: 見送り。devkit 自身の痛み（version bump 忘れ）は既に `check_plugin_version_bump.py` + pre-push gate（梯子の第 2 段）で解決済みで、v7.0.0→7.1.0 のリリースは事故なく回っている。他 repo で同型の摩擦は未観測（証拠テスト不通過）。次にリリース摩擦を観測したら再評価する。
- **review**: 見送り。Claude Code 組み込みの `/code-review` と重複（ハーネス非重複テスト不通過）。
- **debug**: 見送り。ベースエージェントの即興で十分（即興リスクテスト不通過）。
- **test-gap**: 見送り。refactor の棚卸し観点（テスト欠落）として吸収可能（梯子の第 3 段）。

注: auto-memory は repo 外（git 管理外）のファイルであり、本レポートの該当指摘は repo の変更履歴に残らない。
