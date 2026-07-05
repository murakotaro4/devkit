#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const RESET = "\x1b[0m";
const RED = "\x1b[31m";
const YELLOW = "\x1b[33m";
const GREEN = "\x1b[32m";
const CYAN = "\x1b[36m";
const DIM = "\x1b[2m";

const CACHE_TTL_SECONDS = 60;
const CACHE_STALE_SECONDS = 300;
const FX_CACHE_TTL_SECONDS = 86400;
const FX_FAILURE_TTL_SECONDS = 300;
const USAGE_URL = "https://api.anthropic.com/api/oauth/usage";
const FX_URL = "https://open.er-api.com/v6/latest/USD";
const OAUTH_BETA_HEADER = "oauth-2025-04-20";
const CREDENTIAL_SERVICE = "Claude Code-credentials";

let fallbackDir = path.basename(process.cwd()) || "unknown";
let fallbackModel = "unknown";

function diagnostic(tag, message) {
  if (process.env.DEVKIT_STATUSLINE_DEBUG === "1") {
    process.stderr.write(`devkit-statusline[${tag}]: ${message}\n`);
  }
}

function readStdin() {
  try {
    const text = fs.readFileSync(0, "utf8").trim();
    if (!text) {
      return {};
    }
    return JSON.parse(text);
  } catch (error) {
    diagnostic("stdin", "failed to parse status input");
    return {};
  }
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function numberOrNull(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function clampPercent(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return null;
  }
  return Math.max(0, Math.min(100, Math.round(value)));
}

function usedPercentFrom(value) {
  const obj = asObject(value);
  const used = numberOrNull(obj.used_percentage);
  if (used !== null) {
    return clampPercent(used);
  }
  const remaining = numberOrNull(obj.remaining_percentage);
  if (remaining !== null) {
    return clampPercent(100 - remaining);
  }
  const utilization = numberOrNull(obj.utilization);
  if (utilization !== null) {
    return clampPercent(utilization <= 1 ? utilization * 100 : utilization);
  }
  const percent = numberOrNull(obj.percent);
  if (percent !== null) {
    return clampPercent(percent <= 1 ? percent * 100 : percent);
  }
  return null;
}

function colorForUsedPercent(usedPercent) {
  if (usedPercent >= 80) {
    return RED;
  }
  if (usedPercent >= 50) {
    return YELLOW;
  }
  return GREEN;
}

function colorize(text, usedPercent) {
  if (usedPercent === null || usedPercent === undefined) {
    return text;
  }
  return `${colorForUsedPercent(usedPercent)}${text}${RESET}`;
}

function dim(text) {
  return `${DIM}${text}${RESET}`;
}

function basenameOf(dir) {
  if (!dir || typeof dir !== "string") {
    return "unknown";
  }
  return path.basename(dir) || dir || "unknown";
}

function workspaceDir(input) {
  const workspace = asObject(input.workspace);
  return typeof workspace.current_dir === "string" && workspace.current_dir
    ? workspace.current_dir
    : process.cwd();
}

function displayModel(input) {
  const model = asObject(input.model);
  return typeof model.display_name === "string" && model.display_name
    ? model.display_name
    : "unknown";
}

function gitBranch(cwd) {
  if (!cwd) {
    return "";
  }
  try {
    return execFileSync("git", ["rev-parse","--abbrev-ref","HEAD"], {
      cwd,
      timeout:1500,
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString("utf8")
      .trim();
  } catch (error) {
    return "";
  }
}

function epochMillis(value) {
  const numeric = numberOrNull(value);
  if (numeric !== null) {
    return numeric > 100000000000 ? numeric : numeric * 1000;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function formatLocalHHMM(value) {
  const millis = epochMillis(value);
  if (millis === null) {
    return "";
  }
  const date = new Date(millis);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function formatRemainingUntil(value) {
  const millis = epochMillis(value);
  if (millis === null) {
    return "";
  }
  const remainingMillis = millis - Date.now();
  if (remainingMillis <= 0) {
    return "";
  }
  const remainingMinutes = Math.max(1, Math.floor(remainingMillis / 60000));
  if (remainingMinutes >= 1440) {
    const days = Math.floor(remainingMinutes / 1440);
    const hours = Math.floor((remainingMinutes % 1440) / 60);
    return `残り ${days}d${hours}h`;
  }
  if (remainingMinutes >= 60) {
    return `残り ${Math.floor(remainingMinutes / 60)}h`;
  }
  return `残り ${remainingMinutes}m`;
}

function formatAge(seconds) {
  const safeSeconds = Math.max(0, Math.round(seconds));
  if (safeSeconds >= 3600) {
    return `${Math.floor(safeSeconds / 3600)}h ago`;
  }
  return `${Math.max(1, Math.floor(safeSeconds / 60))}m ago`;
}

function initialUsage(input) {
  const contextWindow = asObject(input.context_window);
  const ctxUsed = usedPercentFrom(contextWindow);
  const rateLimits = asObject(input.rate_limits);
  const fiveHour = asObject(rateLimits.five_hour);
  const sevenDay = asObject(rateLimits.seven_day);
  const fiveHourUsed = usedPercentFrom(fiveHour);
  const sevenDayUsed = usedPercentFrom(sevenDay);

  return {
    ctxUsed,
    fiveHour:
      fiveHourUsed === null
        ? null
        : {
            used: fiveHourUsed,
            reset: formatLocalHHMM(fiveHour.resets_at),
            staleAgeSeconds: null,
          },
    sevenDay:
      sevenDayUsed === null
        ? null
        : {
            used: sevenDayUsed,
            resetAtMillis: epochMillis(sevenDay.resets_at),
            staleAgeSeconds: null,
          },
    scoped: [],
  };
}

function cacheFilePath() {
  return path.join(process.env.DEVKIT_STATUSLINE_CACHE_DIR || os.tmpdir(), ".claude-usage-cache.json");
}

function fxCacheFilePath() {
  return path.join(process.env.DEVKIT_STATUSLINE_CACHE_DIR || os.tmpdir(), ".claude-fx-cache.json");
}

function safeLstat(target) {
  try {
    return fs.lstatSync(target);
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return null;
    }
    throw error;
  }
}

function readCache(cacheFile) {
  const stat = safeLstat(cacheFile);
  if (!stat) {
    return null;
  }
  if (stat.isSymbolicLink()) {
    diagnostic("cache", "refusing symlink cache");
    return null;
  }
  if (!stat.isFile()) {
    return null;
  }
  const ageSeconds = Math.max(0, (Date.now() - stat.mtimeMs) / 1000);
  try {
    return {
      data: JSON.parse(fs.readFileSync(cacheFile, "utf8")),
      ageSeconds,
    };
  } catch (error) {
    diagnostic("cache", "failed to read cache");
    return null;
  }
}

function writeCache(cacheFile, data) {
  const existing = safeLstat(cacheFile);
  if (existing && existing.isSymbolicLink()) {
    diagnostic("cache", "refusing to replace symlink cache");
    return;
  }

  const cacheDir = path.dirname(cacheFile);
  fs.mkdirSync(cacheDir, { recursive: true });
  const tmpPrefix = path.basename(cacheFile).replace(/[^A-Za-z0-9._-]/g, "cache");
  const tmpFile = path.join(cacheDir, `${tmpPrefix}.${process.pid}.${Date.now()}.tmp`);
  fs.writeFileSync(tmpFile, `${JSON.stringify(data)}\n`, { mode: 0o600 });
  if (process.platform !== "win32") {
    fs.chmodSync(tmpFile, 0o600);
  }
  fs.renameSync(tmpFile, cacheFile);
  if (process.platform !== "win32") {
    fs.chmodSync(cacheFile, 0o600);
  }
}

function credentialPath() {
  return path.join(homeDir(), ".claude", ".credentials.json");
}

function homeDir() {
  return process.env.HOME || os.homedir();
}

function readAccessToken() {
  if (process.platform === "darwin") {
    const stdout = execFileSync("security", ["find-generic-password", "-s", CREDENTIAL_SERVICE, "-w"], {
      timeout: 1500,
      stdio: ["ignore", "pipe", "ignore"],
    }).toString("utf8");
    return tokenFromCredentialJson(stdout);
  }

  const credentialJson = fs.readFileSync(credentialPath(), "utf8");
  return tokenFromCredentialJson(credentialJson);
}

function tokenFromCredentialJson(text) {
  const credentials = JSON.parse(text);
  const oauth = asObject(credentials.claudeAiOauth);
  return typeof oauth.accessToken === "string" && oauth.accessToken ? oauth.accessToken : "";
}

async function fetchUsage(token) {
  if (typeof fetch !== "function" || typeof AbortSignal === "undefined" || typeof AbortSignal.timeout !== "function") {
    return null;
  }

  const response = await fetch(USAGE_URL, {
    headers: {
      Authorization: `Bearer ${token}`,
      "anthropic-beta": OAUTH_BETA_HEADER,
    },
    signal: AbortSignal.timeout(2000),
  });
  if (!response.ok) {
    diagnostic("usage", `usage API returned HTTP ${response.status}`);
    return null;
  }
  return response.json();
}

async function fetchFxRates() {
  if (typeof fetch !== "function" || typeof AbortSignal === "undefined" || typeof AbortSignal.timeout !== "function") {
    return null;
  }

  const response = await fetch(FX_URL, {
    signal: AbortSignal.timeout(2000),
  });
  if (!response.ok) {
    diagnostic("fx", `FX API returned HTTP ${response.status}`);
    return null;
  }
  return response.json();
}

function apiRateObject(data, key) {
  const obj = asObject(data[key]);
  if (Object.keys(obj).length > 0) {
    return obj;
  }
  return asObject(asObject(data.rate_limits)[key]);
}

function scopedUsageFromApi(data, staleAgeSeconds) {
  const limits = Array.isArray(data.limits) ? data.limits : [];
  for (const limit of limits) {
    const item = asObject(limit);
    if (item.kind !== "weekly_scoped") {
      continue;
    }
    const scope = asObject(item.scope);
    const model = asObject(scope.model);
    const label = typeof model.display_name === "string" && model.display_name ? model.display_name : "";
    const used = usedPercentFrom(item);
    if (label && used !== null) {
      return [{ label, used, staleAgeSeconds }];
    }
  }
  return [];
}

function usageFromApi(data, staleAgeSeconds) {
  const fiveHour = apiRateObject(data, "five_hour");
  const sevenDay = apiRateObject(data, "seven_day");
  const fiveHourUsed = usedPercentFrom(fiveHour);
  const sevenDayUsed = usedPercentFrom(sevenDay);
  return {
    fiveHour:
      fiveHourUsed === null
        ? null
        : {
            used: fiveHourUsed,
            reset: formatLocalHHMM(fiveHour.resets_at),
            staleAgeSeconds,
          },
    sevenDay:
      sevenDayUsed === null
        ? null
        : {
            used: sevenDayUsed,
            resetAtMillis: epochMillis(sevenDay.resets_at),
            staleAgeSeconds,
          },
    scoped: scopedUsageFromApi(data, staleAgeSeconds),
  };
}

async function secondLayerUsage() {
  const cacheFile = cacheFilePath();
  const cached = readCache(cacheFile);
  if (process.env.DEVKIT_STATUSLINE_NO_FETCH === "1") {
    if (cached && cached.ageSeconds < CACHE_TTL_SECONDS) {
      return usageFromApi(cached.data, null);
    }
    if (cached && cached.ageSeconds <= CACHE_STALE_SECONDS) {
      return usageFromApi(cached.data, cached.ageSeconds);
    }
    return null;
  }

  if (cached && cached.ageSeconds < CACHE_TTL_SECONDS) {
    return usageFromApi(cached.data, null);
  }

  try {
    const token = readAccessToken();
    if (token) {
      const fresh = await fetchUsage(token);
      if (fresh) {
        writeCache(cacheFile, fresh);
        return usageFromApi(fresh, null);
      }
    }
  } catch (error) {
    diagnostic("usage", "usage fetch skipped");
  }

  if (cached && cached.ageSeconds <= CACHE_STALE_SECONDS) {
    return usageFromApi(cached.data, cached.ageSeconds);
  }
  return null;
}

function sessionCostUsd(input) {
  const cost = asObject(input.cost);
  const total = numberOrNull(cost.total_cost_usd);
  return total !== null && total >= 0 ? total : null;
}

function jpyRateFromFxData(data) {
  const rate = numberOrNull(asObject(asObject(data).rates).JPY);
  return rate !== null && rate > 0 ? rate : null;
}

function readFxCache(cacheFile) {
  try {
    return readCache(cacheFile);
  } catch (error) {
    diagnostic("fx", "failed to read FX cache");
    return null;
  }
}

function writeFxCache(cacheFile, data) {
  try {
    writeCache(cacheFile, data);
  } catch (error) {
    diagnostic("fx", "failed to write FX cache");
  }
}

async function fxRateForCost(costUsd, canFetch) {
  if (costUsd === null) {
    return null;
  }

  const cacheFile = fxCacheFilePath();
  const cached = readFxCache(cacheFile);
  if (cached) {
    const cachedRate = jpyRateFromFxData(cached.data);
    if (cachedRate !== null && cached.ageSeconds < FX_CACHE_TTL_SECONDS) {
      return cachedRate;
    }
    if (cachedRate === null && cached.ageSeconds < FX_FAILURE_TTL_SECONDS) {
      return null;
    }
  }

  if (!canFetch || process.env.DEVKIT_STATUSLINE_NO_FETCH === "1") {
    return null;
  }

  try {
    const fresh = await fetchFxRates();
    const freshRate = jpyRateFromFxData(fresh);
    if (freshRate !== null) {
      writeFxCache(cacheFile, fresh);
      return freshRate;
    }
    writeFxCache(cacheFile, { fx_error: true });
  } catch (error) {
    diagnostic("fx", "FX fetch skipped");
    writeFxCache(cacheFile, { fx_error: true });
  }
  return null;
}

function mergeUsage(firstLayer, secondLayer) {
  if (!secondLayer) {
    return firstLayer;
  }
  const fiveHour = firstLayer.fiveHour || secondLayer.fiveHour;
  if (firstLayer.fiveHour && secondLayer.fiveHour && !firstLayer.fiveHour.reset && secondLayer.fiveHour.reset) {
    fiveHour.reset = secondLayer.fiveHour.reset;
  }
  const sevenDay = firstLayer.sevenDay || secondLayer.sevenDay;
  if (
    firstLayer.sevenDay &&
    secondLayer.sevenDay &&
    !firstLayer.sevenDay.resetAtMillis &&
    secondLayer.sevenDay.resetAtMillis
  ) {
    sevenDay.resetAtMillis = secondLayer.sevenDay.resetAtMillis;
  }
  return {
    ctxUsed: firstLayer.ctxUsed,
    fiveHour,
    sevenDay,
    scoped: secondLayer.scoped || [],
  };
}

function staleSuffix(item) {
  if (!item || item.staleAgeSeconds === null || item.staleAgeSeconds === undefined) {
    return "";
  }
  return ` ${dim(`(${formatAge(item.staleAgeSeconds)})`)}`;
}

function formatCost(costUsd, jpyRate) {
  if (jpyRate !== null && jpyRate !== undefined) {
    return `¥${String(Math.round(costUsd * jpyRate)).replace(/\B(?=(\d{3})+(?!\d))/g, ",")}`;
  }
  return `$${costUsd.toFixed(2)}`;
}

function renderLine(input, usage, costUsd, jpyRate) {
  const cwd = workspaceDir(input);
  const model = displayModel(input);
  fallbackDir = basenameOf(cwd);
  fallbackModel = model;

  const identityParts = [fallbackDir, model];
  const branch = gitBranch(cwd);
  if (branch) {
    identityParts.push(`${CYAN}${branch}${RESET}`);
  }

  const metricParts = [];
  if (usage.ctxUsed !== null && usage.ctxUsed !== undefined) {
    const remaining = clampPercent(100 - usage.ctxUsed);
    metricParts.push(colorize(`ctx 残り ${remaining}%`, usage.ctxUsed));
  }

  if (usage.fiveHour) {
    const reset = usage.fiveHour.reset ? ` (${usage.fiveHour.reset})` : "";
    metricParts.push(`${colorize(`5hr ${usage.fiveHour.used}%${reset}`, usage.fiveHour.used)}${staleSuffix(usage.fiveHour)}`);
  }

  if (usage.sevenDay) {
    const reset = formatRemainingUntil(usage.sevenDay.resetAtMillis);
    const resetSuffix = reset ? ` (${reset})` : "";
    metricParts.push(`${colorize(`wk ${usage.sevenDay.used}%${resetSuffix}`, usage.sevenDay.used)}${staleSuffix(usage.sevenDay)}`);
  }

  for (const scoped of usage.scoped) {
    metricParts.push(`${colorize(`${scoped.label} ${scoped.used}%`, scoped.used)}${staleSuffix(scoped)}`);
  }

  if (costUsd !== null) {
    metricParts.push(formatCost(costUsd, jpyRate));
  }

  const lines = [identityParts.join(" | ")];
  if (metricParts.length > 0) {
    lines.push(metricParts.join(" | "));
  }
  return lines.join("\n");
}

function fallbackLine() {
  return `${fallbackDir || "unknown"} | ${fallbackModel || "unknown"}`;
}

async function run() {
  const input = readStdin();
  const cwd = workspaceDir(input);
  fallbackDir = basenameOf(cwd);
  fallbackModel = displayModel(input);

  const firstLayer = initialUsage(input);
  const costUsd = sessionCostUsd(input);
  const nodeMajor = Number(String(process.versions.node || "0").split(".")[0]);
  if (!Number.isFinite(nodeMajor) || nodeMajor < 18) {
    diagnostic("node", "Node 18 or newer is required for usage fetch");
    const jpyRate = await fxRateForCost(costUsd, false);
    return renderLine(input, firstLayer, costUsd, jpyRate);
  }

  const [secondLayer, jpyRate] = await Promise.all([secondLayerUsage(), fxRateForCost(costUsd, true)]);
  return renderLine(input, mergeUsage(firstLayer, secondLayer), costUsd, jpyRate);
}

run()
  .then((line) => {
    process.stdout.write(`${line || fallbackLine()}\n`);
    process.exitCode = 0;
  })
  .catch((error) => {
    diagnostic("top", "unexpected failure");
    process.stdout.write(`${fallbackLine()}\n`);
    process.exitCode = 0;
  });
