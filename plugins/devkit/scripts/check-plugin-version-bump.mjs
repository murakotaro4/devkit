#!/usr/bin/env node
import fs from "fs";
import path from "path";
import { execSync } from "child_process";

const root = process.cwd();
const pluginJsonRel = "plugins/devkit/.claude-plugin/plugin.json";
const baseRef = process.env.DIG_VERSION_BASE_REF || "origin/main";

function runGit(args) {
  return execSync(`git ${args}`, {
    cwd: root,
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
  }).trim();
}

function parseVersion(raw, sourceLabel) {
  let json;
  try {
    json = JSON.parse(raw);
  } catch (err) {
    throw new Error(`invalid JSON in ${sourceLabel}: ${err.message}`);
  }
  if (typeof json.version !== "string" || json.version.trim() === "") {
    throw new Error(`version missing in ${sourceLabel}`);
  }
  return json.version.trim();
}

function parseSemver(version) {
  const m = version.match(/^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/);
  if (!m) return null;
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

function compareSemver(a, b) {
  for (let i = 0; i < 3; i += 1) {
    if (a[i] !== b[i]) return a[i] - b[i];
  }
  return 0;
}

function getMergeBase(ref) {
  try {
    return runGit(`merge-base HEAD ${ref}`);
  } catch (err) {
    throw new Error(`cannot resolve merge-base with ${ref}: ${err.message}`);
  }
}

function getChangedFiles(baseSha) {
  const out = runGit(`diff --name-only ${baseSha}...HEAD`);
  if (!out) return [];
  return out.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
}

function requiresVersionGate(changedFiles) {
  return changedFiles.some((f) => {
    const unixPath = f.replace(/\\/g, "/");
    return (
      unixPath.startsWith("plugins/devkit/") ||
      unixPath.startsWith(".claude-plugin/")
    );
  });
}

function readHeadVersion() {
  const abs = path.join(root, pluginJsonRel);
  if (!fs.existsSync(abs)) {
    throw new Error(`missing file: ${pluginJsonRel}`);
  }
  const raw = fs.readFileSync(abs, "utf8").replace(/^\uFEFF/, "");
  return parseVersion(raw, `${pluginJsonRel} (HEAD)`);
}

function readBaseVersion(ref) {
  let raw;
  try {
    raw = runGit(`show ${ref}:${pluginJsonRel}`);
  } catch (err) {
    throw new Error(`cannot read ${pluginJsonRel} from ${ref}: ${err.message}`);
  }
  return parseVersion(raw, `${pluginJsonRel} (${ref})`);
}

function fail(reason, detail = {}) {
  console.error(JSON.stringify({ ok: false, reason, ...detail }, null, 2));
  process.exit(2);
}

function main() {
  const mergeBase = getMergeBase(baseRef);
  const changedFiles = getChangedFiles(mergeBase);

  if (!requiresVersionGate(changedFiles)) {
    console.log(JSON.stringify({
      ok: true,
      skipped: true,
      reason: "no changes under plugins/devkit/** or .claude-plugin/*",
      baseRef,
      mergeBase,
    }, null, 2));
    return;
  }

  const headVersion = readHeadVersion();
  const baseVersion = readBaseVersion(baseRef);

  const parsedHead = parseSemver(headVersion);
  const parsedBase = parseSemver(baseVersion);
  if (!parsedHead || !parsedBase) {
    fail("version must be semver", { headVersion, baseVersion });
  }

  if (compareSemver(parsedHead, parsedBase) <= 0) {
    fail("plugin version not bumped", {
      required: `>${baseVersion}`,
      headVersion,
      baseVersion,
      baseRef,
    });
  }

  console.log(JSON.stringify({
    ok: true,
    skipped: false,
    baseRef,
    baseVersion,
    headVersion,
  }, null, 2));
}

main();
