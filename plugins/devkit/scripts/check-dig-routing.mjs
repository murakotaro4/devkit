#!/usr/bin/env node
import fs from "fs";
import path from "path";

const root = process.cwd();

function mustRead(rel) {
  const abs = path.join(root, rel);
  if (!fs.existsSync(abs)) throw new Error(`Missing file: ${rel}`);
  return fs.readFileSync(abs, "utf8");
}

const dig = mustRead("plugins/devkit/skills/dig/SKILL.md");
const core = mustRead("plugins/devkit/skills/dig-core/SKILL.md");
const claude = mustRead("plugins/devkit/skills/dig-claude/SKILL.md");
const codex = mustRead("plugins/devkit/skills/dig-codex/SKILL.md");
const opencode = mustRead("plugins/devkit/skills/dig-opencode/SKILL.md");
const workflow = mustRead("plugins/devkit/shared/workflow.md");
const agents = mustRead("AGENTS.md");
const readme = mustRead("README.md");

const problems = [];

for (const token of ["dig-core", "dig-claude", "dig-codex", "dig-opencode"]) {
  if (!dig.includes(token)) problems.push(`dig orchestrator missing reference: ${token}`);
}
if (!dig.includes("runtime=<claude|codex|opencode>")) {
  problems.push("dig orchestrator missing runtime contract");
}
if (!dig.includes("Claude `/dig` -> `claude`")) {
  problems.push("dig orchestrator missing Claude default: /dig -> claude");
}
if (!dig.includes("Codex `$dig` -> `codex`")) {
  problems.push("dig orchestrator missing Codex default: $dig -> codex");
}
if (/\/devkit:dig\b/.test(dig)) {
  problems.push("dig orchestrator still references removed command: /devkit:dig");
}
if (/\/prompts:devkit-dig\b/.test(dig)) {
  problems.push("dig orchestrator still references removed command: /prompts:devkit-dig");
}

for (const content of [claude, codex, opencode]) {
  if (!content.includes("dig-core")) problems.push("adapter does not reference dig-core contract");
}

if (!codex.includes("DIG_CODEX_PLAN_REQUIRED")) {
  problems.push("dig-codex missing required stop code");
}
if (!codex.includes("DIG_CODEX_PLAN_REVIEW_UNAVAILABLE")) {
  problems.push("dig-codex missing review unavailable stop code");
}
if (!codex.includes("DIG_CODEX_PLAN_REVIEW_BLOCKED")) {
  problems.push("dig-codex missing review blocked stop code");
}
if (!codex.includes("REVIEW_PRIMARY_CMD")) {
  problems.push("dig-codex missing REVIEW_PRIMARY_CMD marker");
}
if (!codex.includes("REVIEW_FALLBACK_CMD")) {
  problems.push("dig-codex missing REVIEW_FALLBACK_CMD marker");
}
if (codex.includes("/prompts:devkit-dig")) {
  problems.push("dig-codex still references removed command: /prompts:devkit-dig");
}
if (!codex.includes("RERUN_COMMAND: $dig <topic>")) {
  problems.push("dig-codex missing rerun command for $dig");
}

if (!opencode.includes("DIG_OPENCODE_PLAN_AGENT_REQUIRED")) {
  problems.push("dig-opencode missing plan agent stop code");
}
if (!opencode.includes("DIG_OPENCODE_BUILD_REQUIRED")) {
  problems.push("dig-opencode missing build stop code");
}

if (!core.includes("REVIEW_RESULT_MARKER=REVIEW_COUNTS")) {
  problems.push("dig-core missing REVIEW_RESULT_MARKER");
}
if (!core.includes("STOP_OUTPUT_FIELDS: ERROR_CODE,RERUN_COMMAND,DIAGNOSTIC_COMMAND")) {
  problems.push("dig-core missing stop output marker");
}

if (!workflow.includes("gpt-5.3-codex-spark")) {
  problems.push("workflow missing spark review command");
}
if (!workflow.includes("gpt-5.4")) {
  problems.push("workflow missing gpt-5.4 fallback review model");
}
if (!agents.includes("gpt-5.4")) {
  problems.push("AGENTS.md missing gpt-5.4 fallback review model");
}
if (!readme.includes("gpt-5.4")) {
  problems.push("README missing gpt-5.4 fallback review model");
}
if (!workflow.includes("model_reasoning_effort=\"medium\"")) {
  problems.push("workflow missing medium effort fallback");
}
if (!workflow.includes("codex -a never exec review")) {
  problems.push("workflow missing approval-never review command");
}
if (!codex.includes("codex -a never exec review")) {
  problems.push("dig-codex missing approval-never review command");
}
if (!codex.includes("gpt-5.4")) {
  problems.push("dig-codex missing gpt-5.4 fallback review model");
}

if (/\/devkit:dig\b/.test(readme)) {
  problems.push("README still references removed command: /devkit:dig");
}
if (/\/prompts:devkit-dig\b/.test(readme)) {
  problems.push("README still references removed command: /prompts:devkit-dig");
}
if (!readme.includes("DIG_CODEX_PLAN_REVIEW_UNAVAILABLE")) {
  problems.push("README missing unavailable stop code");
}
if (!readme.includes("DIG_CODEX_PLAN_REVIEW_BLOCKED")) {
  problems.push("README missing blocked stop code");
}
if (!readme.includes("codex -a never exec review")) {
  problems.push("README missing approval-never review command");
}

if (problems.length > 0) {
  console.error(JSON.stringify({ ok: false, problems }, null, 2));
  process.exit(2);
}

console.log(JSON.stringify({ ok: true }, null, 2));
