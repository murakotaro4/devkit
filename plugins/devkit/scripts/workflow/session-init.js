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

function normalizeState(state) {
  const phasesPassed = Array.isArray(state?.phases_passed)
    ? state.phases_passed.map(normalizePhaseToken).filter(Boolean)
    : [];

  return {
    ...state,
    workflow_version: 2,
    current_phase_token:
      normalizePhaseToken(state?.current_phase_token) ||
      phasesPassed[phasesPassed.length - 1] ||
      "",
    phases_passed: [...new Set(phasesPassed)],
  };
}

function main() {
  let input = "";
  try {
    if (!process.stdin.isTTY) {
      input = fs.readFileSync(0, "utf8");
    }
  } catch {
    // stdin not available
  }

  let sessionId = "";
  let agentType = "";
  if (input) {
    try {
      const parsed = JSON.parse(input);
      sessionId = parsed.session_id || "";
      agentType = parsed.agent_type || "";
    } catch {
      // malformed input
    }
  }

  // Subagents get lightweight init
  if (agentType === "subagent") {
    const out = {
      hookSpecificOutput: {
        hookEventName: "SessionStart",
        additionalContext: "[devkit-workflow] subagent: skip workflow init",
      },
    };
    process.stdout.write(JSON.stringify(out));
    return;
  }

  // Create or reuse workflow state file
  const claudeDir = path.join(process.env.HOME || "", ".claude");
  sessionId = sanitizeSessionId(sessionId);
  const stateFile = path.join(
    claudeDir,
    `devkit-workflow-${sessionId}.json`
  );

  // Ensure .claude directory exists
  try {
    fs.mkdirSync(claudeDir, { recursive: true });
  } catch {
    // already exists
  }

  // Reuse existing state file if present
  if (fs.existsSync(stateFile)) {
    try {
      const currentState = JSON.parse(fs.readFileSync(stateFile, "utf8"));
      const normalizedState = normalizeState(currentState);
      fs.writeFileSync(stateFile, JSON.stringify(normalizedState, null, 2));
    } catch {
      // ignore migration failure and keep the existing file
    }

    const out = {
      hookSpecificOutput: {
        hookEventName: "SessionStart",
        additionalContext:
          "[devkit-workflow] Existing workflow state loaded. agent-team workflow active.",
      },
    };
    process.stdout.write(JSON.stringify(out));
    return;
  }

  // Create new state file
  const state = {
    workflow_version: 2,
    session_id: sessionId,
    created_at: new Date().toISOString(),
    task: "",
    current_phase_token: "",
    phases_passed: [],
  };

  try {
    fs.writeFileSync(stateFile, JSON.stringify(state, null, 2));
  } catch {
    // write failure is non-fatal
  }

  // Clean up old state files (>24h)
  try {
    const files = fs.readdirSync(claudeDir);
    const now = Date.now();
    const ttl = 24 * 60 * 60 * 1000;
    for (const f of files) {
      if (!f.startsWith("devkit-workflow-")) continue;
      const fp = path.join(claudeDir, f);
      try {
        const stat = fs.statSync(fp);
        if (now - stat.mtimeMs > ttl) {
          fs.unlinkSync(fp);
        }
      } catch {
        // skip
      }
    }
  } catch {
    // cleanup failure is non-fatal
  }

  const out = {
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext:
        "[devkit-workflow] Workflow state initialized. agent-team workflow contract active.",
    },
  };
  process.stdout.write(JSON.stringify(out));
}

main();
