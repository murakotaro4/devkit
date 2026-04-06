#!/usr/bin/env node
"use strict";

const { spawnSync } = require("child_process");
const path = require("path");

const target = process.argv[2];
if (!target) {
  console.error("devkit_hook_runner: missing target script");
  process.exit(2);
}

const pluginRoot = path.resolve(__dirname, "..");
const scriptPath = path.isAbsolute(target) ? target : path.join(pluginRoot, target);
const scriptArgs = process.argv.slice(3);
const candidates = [
  ["uv", ["run", "--project", pluginRoot, "python", scriptPath, ...scriptArgs]],
  ["python", [scriptPath, ...scriptArgs]],
  ["python3", [scriptPath, ...scriptArgs]],
  ["py", ["-3", scriptPath, ...scriptArgs]],
];

for (const [command, args] of candidates) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
  });

  if (result.error) {
    if (result.error.code === "ENOENT") {
      continue;
    }
    console.error(`devkit_hook_runner: failed to launch ${command}: ${result.error.message}`);
    process.exit(1);
  }

  process.exit(result.status === null ? 1 : result.status);
}

console.error(
  "devkit_hook_runner: no supported runtime found. Install uv or a Python interpreter to run DevKit hooks."
);
process.exit(1);
