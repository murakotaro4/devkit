#!/usr/bin/env node
import fs from "fs";
import path from "path";

const root = process.cwd();
const phaseArg = process.argv.find((a) => a.startsWith("--phase="));
const phase = phaseArg ? phaseArg.split("=")[1] : "B";

function readJson(rel) {
  const raw = fs.readFileSync(path.join(root, rel), "utf8").replace(/^\uFEFF/, "");
  return JSON.parse(raw);
}

const required = [
  "plugins/devkit/skills/dig/SKILL.md",
  "plugins/devkit/skills/dig-core/SKILL.md",
  "plugins/devkit/skills/dig-claude/SKILL.md",
  "plugins/devkit/skills/dig-codex/SKILL.md",
  "plugins/devkit/skills/dig-opencode/SKILL.md",
  "plugins/devkit/templates/codex/prompts/devkit-dig.md",
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

if (phase === "B") {
  for (const rel of removed) {
    if (fs.existsSync(path.join(root, rel))) problems.push(`must be removed in phase B: ${rel}`);
  }
}

let readme = fs.readFileSync(path.join(root, "README.md"), "utf8");
readme = readme.replace(/##\s+Migration Notice[\s\S]*?(?=\n##\s+|$)/m, "");
if (/\/devkit:codex(?!-)\b/.test(readme) || /\/devkit:agent-orch-/.test(readme)) {
  problems.push("README still references removed slash commands");
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
