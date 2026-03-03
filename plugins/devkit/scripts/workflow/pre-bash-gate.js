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

function emitDecision(decision, reason, additionalContext) {
  const out = {
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: decision,
      permissionDecisionReason: reason,
    },
  };
  if (additionalContext) {
    out.hookSpecificOutput.additionalContext = additionalContext;
  }
  process.stdout.write(JSON.stringify(out));
}

function findPluginJsonRelPath() {
  try {
    const { execSync } = require("child_process");
    const repoRoot = execSync("git rev-parse --show-toplevel", {
      encoding: "utf8",
      timeout: 5000,
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();

    const candidates = [
      "plugins/devkit/.claude-plugin/plugin.json",
      ".claude-plugin/plugin.json",
    ];
    for (const c of candidates) {
      if (fs.existsSync(path.join(repoRoot, c))) return c;
    }
  } catch {
    // not in a git repo
  }
  return null;
}

function getGitVersion(ref, relPath) {
  try {
    const { execSync } = require("child_process");
    const output = execSync(`git show ${ref}:${relPath}`, {
      encoding: "utf8",
      timeout: 5000,
      stdio: ["pipe", "pipe", "pipe"],
    });
    const data = JSON.parse(output);
    return data.version || null;
  } catch {
    return null;
  }
}

function suggestVersion(currentVersion) {
  const { execSync } = require("child_process");
  const [major, minor, patch] = currentVersion.split(".").map(Number);

  try {
    const log = execSync("git log HEAD --format=%s -20", {
      encoding: "utf8",
      timeout: 5000,
    });
    const messages = log.trim().split("\n");

    let hasBreaking = false;
    let hasFeat = false;

    for (const msg of messages) {
      if (/^.*!:/.test(msg) || /BREAKING CHANGE/.test(msg)) hasBreaking = true;
      if (/^feat(\(.*\))?:/.test(msg)) hasFeat = true;
      if (/^chore.*bump version/.test(msg)) break;
    }

    if (hasBreaking)
      return { version: `${major + 1}.0.0`, reason: "BREAKING CHANGE 検出" };
    if (hasFeat)
      return {
        version: `${major}.${minor + 1}.0`,
        reason: "feat コミット検出",
      };
    return {
      version: `${major}.${minor}.${patch + 1}`,
      reason: "デフォルト patch",
    };
  } catch {
    return {
      version: `${major}.${minor}.${patch + 1}`,
      reason: "デフォルト patch",
    };
  }
}

function checkVersionBump() {
  const relPath = findPluginJsonRelPath();
  if (!relPath) {
    return { blocked: false };
  }

  const headVersion = getGitVersion("HEAD", relPath);
  const remoteVersion = getGitVersion("origin/main", relPath);

  if (!headVersion || !remoteVersion) {
    return { blocked: false };
  }

  if (headVersion === remoteVersion) {
    const recommended = suggestVersion(remoteVersion);
    return {
      blocked: true,
      message: `[devkit-workflow] ⛔ git push がブロックされました。plugin.json のバージョンが変更されていません（現在: ${remoteVersion}）。\n推奨バージョン: ${recommended.version}（理由: ${recommended.reason}）\nplugin.json の version を更新してからコミットし直してください。`,
    };
  }

  return { blocked: false };
}

function main() {
  let input = "";
  try {
    if (!process.stdin.isTTY) {
      input = fs.readFileSync(0, "utf8");
    }
  } catch {
    emitDecision("pass", "stdin not available");
    return;
  }

  if (!input) {
    emitDecision("pass", "no input");
    return;
  }

  let toolInput = {};
  let sessionId = "";
  try {
    const parsed = JSON.parse(input);
    toolInput = parsed.tool_input || {};
    sessionId = sanitizeSessionId(parsed.session_id || "");
  } catch {
    emitDecision("pass", "malformed input");
    return;
  }

  const command = toolInput.command || "";
  if (!command) {
    emitDecision("pass", "no command");
    return;
  }

  // Detect git commit or git push commands
  // Matches: git commit, git -C /path commit, git commit && ..., git commit; ..., etc.
  const isGitCommit = /\bgit\b.*\bcommit(?:\s|$|[;&|])/.test(command);
  const isGitPush = /\bgit\b.*\bpush(?:\s|$|[;&|])/.test(command);

  if (!isGitCommit && !isGitPush) {
    emitDecision("pass", "not a git commit/push");
    return;
  }

  // Check workflow state file for review completion
  const claudeDir = path.join(process.env.HOME || "", ".claude");
  const stateFile = path.join(
    claudeDir,
    `devkit-workflow-${sessionId}.json`
  );

  let state = null;
  try {
    if (fs.existsSync(stateFile)) {
      state = JSON.parse(fs.readFileSync(stateFile, "utf8"));
    }
  } catch {
    // state file unreadable
  }

  // If no state file exists, ask for confirmation
  if (!state) {
    const action = isGitCommit ? "commit" : "push";
    emitDecision(
      "ask",
      `git ${action} detected without workflow state`,
      `[devkit-workflow] \u26a0\ufe0f git ${action} \u304c\u691c\u51fa\u3055\u308c\u307e\u3057\u305f\u3002\u30ef\u30fc\u30af\u30d5\u30ed\u30fc\u72b6\u614b\u304c\u78ba\u8a8d\u3067\u304d\u307e\u305b\u3093\u3002\u30ec\u30d3\u30e5\u30fc\u30d5\u30a7\u30fc\u30ba\uff08Phase 5/7\uff09\u3092\u5b8c\u4e86\u3057\u3066\u3044\u307e\u3059\u304b\uff1f`
    );
    return;
  }

  const phasesPassed = Array.isArray(state.phases_passed)
    ? state.phases_passed
    : [];
  const hasReview =
    phasesPassed.includes("plan_review") &&
    phasesPassed.includes("impl_review");

  if (isGitCommit && !hasReview) {
    emitDecision(
      "ask",
      "git commit detected without review phase marker",
      `[devkit-workflow] \u26a0\ufe0f git commit \u304c\u691c\u51fa\u3055\u308c\u307e\u3057\u305f\u304c\u3001\u30ec\u30d3\u30e5\u30fc\u30d5\u30a7\u30fc\u30ba\u306e\u5b8c\u4e86\u30de\u30fc\u30ab\u30fc\u304c\u3042\u308a\u307e\u305b\u3093\u3002\n8\u30d5\u30a7\u30fc\u30ba\u30ef\u30fc\u30af\u30d5\u30ed\u30fc\u306e Phase 5\uff08\u8a08\u753b\u30ec\u30d3\u30e5\u30fc\uff09\u307e\u305f\u306f Phase 7\uff08\u5b9f\u88c5\u30ec\u30d3\u30e5\u30fc\uff09\u3092\u5b8c\u4e86\u3057\u3066\u304b\u3089\u30b3\u30df\u30c3\u30c8\u3057\u3066\u304f\u3060\u3055\u3044\u3002`
    );
    return;
  }

  if (isGitPush && !phasesPassed.includes("commit_review")) {
    emitDecision(
      "ask",
      "git push detected without commit review marker",
      `[devkit-workflow] \u26a0\ufe0f git push \u304c\u691c\u51fa\u3055\u308c\u307e\u3057\u305f\u304c\u3001\u30b3\u30df\u30c3\u30c8\u524d\u30ec\u30d3\u30e5\u30fc\uff08Phase 8 Step 2\uff09\u306e\u5b8c\u4e86\u30de\u30fc\u30ab\u30fc\u304c\u3042\u308a\u307e\u305b\u3093\u3002`
    );
    return;
  }

  // Version bump check for git push
  if (isGitPush) {
    const versionCheck = checkVersionBump();
    if (versionCheck.blocked) {
      emitDecision(
        "block",
        "plugin.json version not bumped",
        versionCheck.message
      );
      return;
    }
  }

  // All checks passed
  emitDecision("pass", "workflow checks passed");
}

main();
