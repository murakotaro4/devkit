#!/usr/bin/env node
import fs from "fs";
import path from "path";
import os from "os";
import crypto from "crypto";
import { execFileSync } from "child_process";

const args = process.argv.slice(2);
const modeArg = args.find((a) => a.startsWith("--mode="));
const artifactArg = args.find((a) => a.startsWith("--artifact="));
const mode = modeArg ? modeArg.split("=")[1] : "repo";
const artifactPath = artifactArg ? artifactArg.split("=")[1] : "";

const root = process.cwd();
const legacyPatterns = [
  /\/devkit:codex(?!-)\b/g,
  /\/devkit:agent-orch-(core|openai|anthropic|google)\b/g,
  /devkit-codex(?!-)\b/g,
  /devkit-agent-orch-core\b/g,
  /agent-orch-(core|openai|anthropic|google)\b/g,
  /plugins\/devkit\/skills\/codex\b/g,
  /plugins\/devkit\/skills\/agent-orch-(core|openai|anthropic|google)\b/g,
];

const textExt = new Set([
  ".md", ".txt", ".json", ".yaml", ".yml", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh", ".ps1", ".bat", ".cmd", ".toml", ".ini", ".cfg", ".py"
]);

function isBinaryBuffer(buf) {
  const max = Math.min(buf.length, 8000);
  for (let i = 0; i < max; i += 1) {
    if (buf[i] === 0) return true;
  }
  return false;
}

function collectFiles(dir, out = []) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const e of entries) {
    if (e.name === ".git" || e.name === "node_modules" || e.name === ".claude" || e.name === ".codex") continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) collectFiles(p, out);
    else out.push(p);
  }
  return out;
}

function isAllowedException(fileRel, line, readmeSectionState) {
  if (line.includes("migration-allow")) return true;
  if (fileRel === "CHANGELOG.md") return true;
  if (fileRel === "README.md") {
    return readmeSectionState.inMigrationNotice;
  }
  return false;
}

function scanTextFile(absPath, relPath) {
  const content = fs.readFileSync(absPath, "utf8");
  const lines = content.split(/\r?\n/);
  const findings = [];
  const readmeState = { inMigrationNotice: false };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];

    if (relPath === "README.md") {
      if (/^##\s+Migration Notice\b/.test(line)) {
        readmeState.inMigrationNotice = true;
      } else if (/^##\s+/.test(line) && readmeState.inMigrationNotice) {
        readmeState.inMigrationNotice = false;
      }
    }

    for (const pat of legacyPatterns) {
      const m = line.match(pat);
      if (!m) continue;
      if (isAllowedException(relPath, line, readmeState)) continue;
      findings.push({
        path: relPath,
        line: i + 1,
        token: m[0],
        replacement: "Use /dig runtime adapters and new templates",
      });
    }
  }

  return findings;
}

function scanDir(dir) {
  const findings = [];
  const binaries = [];
  const files = collectFiles(dir);

  for (const file of files) {
    const rel = path.relative(root, file).replace(/\\/g, "/");
    if (rel.startsWith("plugins/devkit/scripts/check-dig-migration.mjs")) continue;
    if (rel.startsWith("plugins/devkit/scripts/check-skill-surface.mjs")) continue;
    if (rel.startsWith("plugins/devkit/scripts/check-dig-routing.mjs")) continue;
    const ext = path.extname(file).toLowerCase();

    const buf = fs.readFileSync(file);
    if (isBinaryBuffer(buf) || !textExt.has(ext)) {
      const hash = crypto.createHash("sha256").update(buf).digest("hex");
      binaries.push({ path: rel, sha256: hash });
      continue;
    }

    findings.push(...scanTextFile(file, rel));
  }

  return { findings, binaries };
}

function extractArtifact(artifact, tempDir) {
  const lower = artifact.toLowerCase();
  if (lower.endsWith(".zip")) {
    if (process.platform === "win32") {
      execFileSync("powershell", ["-NoProfile", "-Command", `Expand-Archive -Path \"${artifact}\" -DestinationPath \"${tempDir}\" -Force`], { stdio: "inherit" });
    } else {
      execFileSync("unzip", ["-o", artifact, "-d", tempDir], { stdio: "inherit" });
    }
    return;
  }
  if (lower.endsWith(".tar") || lower.endsWith(".tgz") || lower.endsWith(".tar.gz")) {
    execFileSync("tar", ["-xf", artifact, "-C", tempDir], { stdio: "inherit" });
    return;
  }
  throw new Error(`Unsupported artifact type: ${artifact}`);
}

function main() {
  let result;

  if (mode === "repo") {
    result = scanDir(root);
  } else if (mode === "artifact") {
    if (!artifactPath) throw new Error("--artifact is required in artifact mode");
    const absArtifact = path.resolve(root, artifactPath);
    if (!fs.existsSync(absArtifact)) throw new Error(`Artifact not found: ${absArtifact}`);
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "dig-mig-"));
    extractArtifact(absArtifact, tmp);
    result = scanDir(tmp);
  } else {
    throw new Error(`Unknown mode: ${mode}`);
  }

  const out = {
    mode,
    findings: result.findings,
    binaryEntries: result.binaries,
  };

  console.log(JSON.stringify(out, null, 2));

  if (result.findings.length > 0) {
    process.exit(2);
  }
}

main();
