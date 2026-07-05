#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

const SCRIPT_NAME = "devkit-statusline.js";
const SETTINGS_NAME = "settings.json";

function usage() {
  process.stderr.write("usage: node install.js [--check] [--force]\n");
}

function parseArgs(argv) {
  const options = { check: false, force: false };
  for (const arg of argv) {
    if (arg === "--check") {
      options.check = true;
    } else if (arg === "--force") {
      options.force = true;
    } else {
      usage();
      process.exit(2);
    }
  }
  return options;
}

function normalizedHome() {
  return homeDir().replace(/\\/g, "/");
}

function claudeDir() {
  return path.join(homeDir(), ".claude");
}

function homeDir() {
  return process.env.HOME || os.homedir();
}

function managedScriptPath() {
  return path.join(claudeDir(), SCRIPT_NAME);
}

function settingsPath() {
  return path.join(claudeDir(), SETTINGS_NAME);
}

function managedCommand() {
  return `node "${normalizedHome()}/.claude/${SCRIPT_NAME}"`;
}

function managedStatusLine() {
  return {
    type: "command",
    command: managedCommand(),
    padding: 0,
  };
}

function readSettings(filePath) {
  if (!fs.existsSync(filePath)) {
    return {};
  }
  const text = fs.readFileSync(filePath, "utf8").trim();
  if (!text) {
    return {};
  }
  return JSON.parse(text);
}

function isDevkitStatusLine(statusLine) {
  return (
    statusLine &&
    typeof statusLine === "object" &&
    statusLine.type === "command" &&
    typeof statusLine.command === "string" &&
    statusLine.command === managedCommand()
  );
}

function stateFor(settings) {
  if (!Object.prototype.hasOwnProperty.call(settings, "statusLine")) {
    return "not-installed";
  }
  return isDevkitStatusLine(settings.statusLine) ? "managed" : "foreign";
}

function writeJsonAtomic(filePath, value) {
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });
  const tmpFile = path.join(dir, `${path.basename(filePath)}.${process.pid}.${Date.now()}.tmp`);
  fs.writeFileSync(tmpFile, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  fs.renameSync(tmpFile, filePath);
}

function copyManagedScript() {
  const source = path.join(__dirname, "statusline.js");
  const target = managedScriptPath();
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(source, target);
}

function checkPayload(state, settings) {
  const payload = {
    state,
    settings: settingsPath().replace(/\\/g, "/"),
    target: managedScriptPath().replace(/\\/g, "/"),
  };
  if (settings.statusLine !== undefined) {
    payload.statusLine = settings.statusLine;
  }
  return payload;
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const settingsFile = settingsPath();
  const settings = readSettings(settingsFile);
  const state = stateFor(settings);

  if (options.check) {
    process.stdout.write(`${JSON.stringify(checkPayload(state, settings))}\n`);
    return 0;
  }

  if (state === "foreign" && !options.force) {
    process.stderr.write(`foreign statusLine detected: ${JSON.stringify(settings.statusLine)}\n`);
    return 3;
  }

  copyManagedScript();
  const nextSettings = {
    ...settings,
    statusLine: managedStatusLine(),
  };
  writeJsonAtomic(settingsFile, nextSettings);
  process.stdout.write(`${JSON.stringify(checkPayload("managed", nextSettings))}\n`);
  return 0;
}

try {
  process.exitCode = main();
} catch (error) {
  process.stderr.write(`devkit statusline install failed: ${error && error.message ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
