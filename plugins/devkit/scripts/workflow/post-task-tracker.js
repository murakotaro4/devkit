#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const LEGACY_PHASE_MAP = {
  plan_review: "plan_review_completed",
  impl_review: "implementation_review_completed",
  commit_review: "commit_review_completed",
  phase_6: "implementation_completed",
};

function sanitizeSessionId(id) {
  if (!id) return crypto.randomUUID();
  const sanitized = id.replace(/[^a-zA-Z0-9-]/g, "");
  return sanitized || crypto.randomUUID();
}

function normalizePhaseToken(token) {
  if (!token || typeof token !== "string") return null;
  return LEGACY_PHASE_MAP[token] || token;
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
    phases = metadata.phases
      .map(normalizePhaseToken)
      .filter(Boolean);
  } else if (typeof metadata.phase === "string" && metadata.phase) {
    phases = [normalizePhaseToken(metadata.phase)].filter(Boolean);
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
    ? state.phases_passed.map(normalizePhaseToken).filter(Boolean)
    : [];
  const merged = [...new Set([...existing, ...phases])];
  const latestPhase = phases[phases.length - 1];
  state.workflow_version = 2;
  state.current_phase_token = latestPhase;
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
      additionalContext: `[devkit-workflow] Phase completed: ${phaseList}. current_phase_token: ${latestPhase}. phases_passed: [${merged.join(", ")}]`,
    },
  };
  process.stdout.write(JSON.stringify(out));
}

main();
