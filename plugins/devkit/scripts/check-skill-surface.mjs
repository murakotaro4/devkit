#!/usr/bin/env node
import fs from "fs";
import os from "os";
import path from "path";
import { execFileSync } from "child_process";

const root = process.cwd();
const phaseArg = process.argv.find((a) => a.startsWith("--phase="));
const phase = phaseArg ? phaseArg.split("=")[1] : "B";

function readJson(rel) {
  const raw = fs.readFileSync(path.join(root, rel), "utf8").replace(/^\uFEFF/, "");
  return JSON.parse(raw);
}

function extractBlock(content, startToken, endToken = "\nfunction ") {
  const start = content.indexOf(startToken);
  if (start === -1) return "";
  const afterStart = content.slice(start);
  const nextFunction = afterStart.indexOf(endToken);
  return nextFunction === -1 ? afterStart : afterStart.slice(0, nextFunction);
}

function bashQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

function runRuntimeSmokeChecks() {
  const runtimeSyncSh = path.join(root, "plugins/devkit/scripts/devkit-runtime-sync.sh");
  const scriptDir = path.dirname(runtimeSyncSh);

  const fallbackHome = fs.mkdtempSync(path.join(os.tmpdir(), "devkit-fallback-"));
  try {
    execFileSync(
      "bash",
      [
        "-lc",
        [
          "set -euo pipefail",
          `export HOME=${bashQuote(fallbackHome)}`,
          "export DEVKIT_REPO_URL='/definitely/missing/devkit.git'",
          `SCRIPT_DIR=${bashQuote(scriptDir)}`,
          `source ${bashQuote(runtimeSyncSh)}`,
          "ROOT=$(ensure_devkit_repo_root)",
          `test "$ROOT" = ${bashQuote(root)}`,
          'test ! -e "$HOME/cursor/devkit"',
        ].join("\n"),
      ],
      { cwd: root, stdio: "pipe", env: process.env },
    );
  } finally {
    fs.rmSync(fallbackHome, { recursive: true, force: true });
  }

  const cleanupHome = fs.mkdtempSync(path.join(os.tmpdir(), "devkit-cleanup-"));
  try {
    execFileSync(
      "bash",
      [
        "-lc",
        [
          "set -euo pipefail",
          `export HOME=${bashQuote(cleanupHome)}`,
          `export DEVKIT_SOURCE_ROOT=${bashQuote(root)}`,
          `SCRIPT_DIR=${bashQuote(scriptDir)}`,
          'mkdir -p "$HOME/.codex/skills" "$HOME/.agents"',
          `ln -s ${bashQuote(path.join(root, "plugins/devkit/skills/dig"))} "$HOME/.codex/skills/dig"`,
          `ln -s ${bashQuote(path.join(root, "plugins/devkit/skills/dig-core"))} "$HOME/.codex/skills/dig-core"`,
          'mkdir -p "$HOME/.codex/skills/custom-keep"',
          `source ${bashQuote(runtimeSyncSh)}`,
          'sync_devkit_codex_runtime "$HOME"',
          'test -L "$HOME/.agents/skills/dig"',
          'test ! -e "$HOME/.codex/skills/dig"',
          'test ! -e "$HOME/.codex/skills/dig-core"',
          'test -d "$HOME/.codex/skills/custom-keep"',
        ].join("\n"),
      ],
      { cwd: root, stdio: "pipe", env: process.env },
    );
  } finally {
    fs.rmSync(cleanupHome, { recursive: true, force: true });
  }
}

const required = [
  "plugins/devkit/skills/dig/SKILL.md",
  "plugins/devkit/skills/dig-core/SKILL.md",
  "plugins/devkit/skills/dig-claude/SKILL.md",
  "plugins/devkit/skills/dig-codex/SKILL.md",
  "plugins/devkit/skills/dig-opencode/SKILL.md",
  "plugins/devkit/scripts/devkit-runtime-sync.sh",
  "plugins/devkit/scripts/devkit-runtime-sync.ps1",
  "plugins/devkit/templates/opencode/commands/dig.md",
  "plugins/devkit/.claude-plugin/plugin.json",
  "plugins/devkit/.claude-plugin/marketplace.json",
  "README.md",
];

const removed = [
  "plugins/devkit/skills/agent-orch-core",
  "plugins/devkit/skills/agent-orch-openai",
  "plugins/devkit/skills/agent-orch-anthropic",
  "plugins/devkit/skills/agent-orch-google",
  "plugins/devkit/skills/codex",
];

const problems = [];
for (const rel of required) {
  if (!fs.existsSync(path.join(root, rel))) problems.push(`missing required: ${rel}`);
}

const digSkills = [
  "plugins/devkit/skills/dig/SKILL.md",
  "plugins/devkit/skills/dig-core/SKILL.md",
  "plugins/devkit/skills/dig-claude/SKILL.md",
  "plugins/devkit/skills/dig-codex/SKILL.md",
  "plugins/devkit/skills/dig-opencode/SKILL.md",
];

for (const rel of digSkills) {
  const abs = path.join(root, rel);
  if (!fs.existsSync(abs)) continue;
  const buf = fs.readFileSync(abs);
  if (buf.length >= 3 && buf[0] === 0xef && buf[1] === 0xbb && buf[2] === 0xbf) {
    problems.push(`BOM not allowed in dig skill frontmatter: ${rel}`);
  }
}

if (phase === "B") {
  for (const rel of removed) {
    if (fs.existsSync(path.join(root, rel))) problems.push(`must be removed in phase B: ${rel}`);
  }
}

let readme = fs.readFileSync(path.join(root, "README.md"), "utf8");
const agents = fs.readFileSync(path.join(root, "AGENTS.md"), "utf8");
const workflow = fs.readFileSync(path.join(root, "plugins/devkit/shared/workflow.md"), "utf8");
const dig = fs.readFileSync(path.join(root, "plugins/devkit/skills/dig/SKILL.md"), "utf8");
readme = readme.replace(/##\s+Migration Notice[\s\S]*?(?=\n##\s+|$)/m, "");
if (/\/devkit:codex(?!-)\b/.test(readme) || /\/devkit:agent-orch-/.test(readme)) {
  problems.push("README still references removed slash commands");
}
if (/\/devkit:dig\b/.test(readme)) problems.push("README still references removed command: /devkit:dig");
if (/\/prompts:devkit-dig\b/.test(readme)) problems.push("README still references removed command: /prompts:devkit-dig");
if (/\/devkit:dig\b/.test(dig)) problems.push("dig skill still references removed command: /devkit:dig");
if (/\/prompts:devkit-dig\b/.test(dig)) problems.push("dig skill still references removed command: /prompts:devkit-dig");
for (const token of ["DIG_CODEX_PLAN_REVIEW_UNAVAILABLE", "DIG_CODEX_PLAN_REVIEW_BLOCKED"]) {
  if (!readme.includes(token)) problems.push(`README missing dig-codex stop code: ${token}`);
  if (!workflow.includes(token)) problems.push(`workflow missing dig-codex stop code: ${token}`);
}
if (!workflow.includes("gpt-5.3-codex-spark")) problems.push("workflow missing spark review model");
if (!workflow.includes("gpt-5.4")) problems.push("workflow missing gpt-5.4 fallback review model");
if (!agents.includes("gpt-5.4")) problems.push("AGENTS.md missing gpt-5.4 fallback review model");
if (!readme.includes("gpt-5.4")) problems.push("README missing gpt-5.4 fallback review model");
if (!workflow.includes("model_reasoning_effort=\"medium\"")) problems.push("workflow missing medium effort fallback");
if (!workflow.includes("codex -a never exec review")) problems.push("workflow missing approval-never review command");

const digCodex = fs.readFileSync(path.join(root, "plugins/devkit/skills/dig-codex/SKILL.md"), "utf8");
if (!digCodex.includes("gpt-5.4")) problems.push("dig-codex missing gpt-5.4 fallback review model");

const runtimeSyncSh = fs.readFileSync(path.join(root, "plugins/devkit/scripts/devkit-runtime-sync.sh"), "utf8");
const runtimeSyncPs1 = fs.readFileSync(path.join(root, "plugins/devkit/scripts/devkit-runtime-sync.ps1"), "utf8");
const shellManifest = extractBlock(runtimeSyncSh, "devkit_skill_manifest() {", "\ndevkit_retired_skill_entries() {");
const psManifest = extractBlock(runtimeSyncPs1, "function Get-DevKitSkillManifest {");

for (const manifest of [
  { name: "devkit-runtime-sync.sh", content: shellManifest },
  { name: "devkit-runtime-sync.ps1", content: psManifest },
]) {
  if (!manifest.content.includes("dig")) problems.push(`${manifest.name} missing public dig entry`);
  for (const token of ["dig-core", "dig-claude", "dig-codex", "dig-opencode"]) {
    if (manifest.content.includes(`"${token}"`) || manifest.content.includes(`${token} \\`) || manifest.content.includes(`    ${token}`)) {
      problems.push(`${manifest.name} still syncs internal dig adapter: ${token}`);
    }
  }
}

if (!runtimeSyncSh.includes("cursor/devkit") && !runtimeSyncPs1.includes("cursor\\devkit")) {
  problems.push("runtime sync scripts missing canonical ~/cursor/devkit source root");
}

try {
  runRuntimeSmokeChecks();
} catch (error) {
  problems.push(`runtime sync smoke failed: ${error.message}`);
}

const plugin = readJson("plugins/devkit/.claude-plugin/plugin.json");
if (typeof plugin.version !== "string") problems.push("plugin.json version missing");
if (/agent-orch/i.test(plugin.description || "")) problems.push("plugin description still references agent-orch");

const market = readJson("plugins/devkit/.claude-plugin/marketplace.json");
const desc = market?.plugins?.[0]?.description || "";
if (/agent-orch/i.test(desc)) problems.push("marketplace description still references agent-orch");

if (problems.length > 0) {
  console.error(JSON.stringify({ phase, problems }, null, 2));
  process.exit(2);
}

console.log(JSON.stringify({ phase, ok: true }, null, 2));
