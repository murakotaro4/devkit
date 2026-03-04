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

const problems = [];

for (const token of ["dig-core", "dig-claude", "dig-codex", "dig-opencode"]) {
  if (!dig.includes(token)) problems.push(`dig orchestrator missing reference: ${token}`);
}
if (!/runtime=<claude\|codex\|opencode>/.test(dig) && !/runtime=claude/.test(dig)) {
  problems.push("dig orchestrator missing runtime contract");
}
for (const content of [claude, codex, opencode]) {
  if (!content.includes("dig-core")) problems.push("adapter does not reference dig-core contract");
}
if (!codex.includes("DIG_CODEX_PLAN_REQUIRED")) problems.push("dig-codex missing required stop code");
if (!opencode.includes("DIG_OPENCODE_PLAN_AGENT_REQUIRED")) problems.push("dig-opencode missing plan agent stop code");
if (!opencode.includes("DIG_OPENCODE_BUILD_REQUIRED")) problems.push("dig-opencode missing build stop code");
if (!core.includes("共通ステップ")) problems.push("dig-core missing common step section");

if (problems.length > 0) {
  console.error(JSON.stringify({ ok: false, problems }, null, 2));
  process.exit(2);
}

console.log(JSON.stringify({ ok: true }, null, 2));
