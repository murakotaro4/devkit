#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

function sanitizeSessionId(id) {
  if (!id) return crypto.randomUUID();
  const sanitized = id.replace(/[^a-zA-Z0-9-]/g, "");
  return sanitized || crypto.randomUUID();
}

function main() {
  let input = "";
  try {
    if (!process.stdin.isTTY) {
      input = fs.readFileSync(0, "utf8");
    }
  } catch {
    return;
  }

  if (!input) return;

  let toolInput = {};
  let sessionId = "";
  try {
    const parsed = JSON.parse(input);
    toolInput = parsed.tool_input || {};
    sessionId = parsed.session_id || "";
  } catch {
    return;
  }

  // Only process TaskUpdate with status="completed" and phase metadata
  if (toolInput.status !== "completed") return;

  const metadata = toolInput.metadata || {};
  let phases = [];

  if (Array.isArray(metadata.phases)) {
    phases = metadata.phases.filter((p) => typeof p === "string" && p);
  } else if (typeof metadata.phase === "string" && metadata.phase) {
    phases = [metadata.phase];
  }

  if (phases.length === 0) return;

  // Update workflow state file
  sessionId = sanitizeSessionId(sessionId);
  const claudeDir = path.join(process.env.HOME || "", ".claude");
  try {
    fs.mkdirSync(claudeDir, { recursive: true });
  } catch {
    // already exists
  }
  const stateFile = path.join(
    claudeDir,
    `devkit-workflow-${sessionId}.json`
  );

  let state = {};
  try {
    if (fs.existsSync(stateFile)) {
      state = JSON.parse(fs.readFileSync(stateFile, "utf8"));
    }
  } catch {
    // corrupted file, start fresh
  }

  const existing = Array.isArray(state.phases_passed)
    ? state.phases_passed
    : [];
  const merged = [...new Set([...existing, ...phases])];
  state.phases_passed = merged;

  try {
    fs.writeFileSync(stateFile, JSON.stringify(state, null, 2));
  } catch {
    // write failure is non-fatal
  }

  const phaseList = phases.join(", ");
  const out = {
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: `[devkit-workflow] Phase completed: ${phaseList}. phases_passed: [${merged.join(", ")}]`,
    },
  };
  process.stdout.write(JSON.stringify(out));
}

main();
