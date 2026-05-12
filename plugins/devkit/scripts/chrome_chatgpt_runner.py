#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CHATGPT_URL = "https://chatgpt.com/"
LOCAL_BYPASS_HOSTS = {"localhost", "127.0.0.1", "::1"}
LINUX_CHROME_PROCESS_NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]


@dataclass(frozen=True)
class ChromeLayout:
    os_name: str
    chrome_path: Path | None
    user_data_dir: Path
    profile_dir: Path
    launch_args: list[str]


@dataclass(frozen=True)
class BrowserBackend:
    name: str
    agent_browser_base: list[str] | None = None


def find_first_existing(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def default_chrome_layout(port: int) -> ChromeLayout:
    system = platform.system().lower()
    home = Path.home()

    if system == "windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        chrome = find_first_existing(
            [
                Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
                Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
                local / "Google/Chrome/Application/chrome.exe",
            ]
        )
        user_data = local / "Google/Chrome/User Data"
        os_name = "windows"
    elif system == "darwin":
        chrome = find_first_existing(
            [
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                home / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ]
        )
        user_data = home / "Library/Application Support/Google/Chrome"
        os_name = "macos"
    else:
        chrome_cmd = shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chrome")
        chrome = Path(chrome_cmd) if chrome_cmd else None
        user_data = home / ".config/google-chrome"
        os_name = "linux"

    profile_dir = user_data / "Default"
    launch_args = [
        str(chrome) if chrome else "google-chrome",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data}",
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        CHATGPT_URL,
    ]
    return ChromeLayout(os_name=os_name, chrome_path=chrome, user_data_dir=user_data, profile_dir=profile_dir, launch_args=launch_args)


def cdp_get(path: str, port: int, timeout: float = 2.5) -> Any | None:
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None


def cdp_available(port: int) -> bool:
    return bool(cdp_get("/json/version", port))


def proxy_bypass_status() -> dict[str, Any]:
    env_values = {
        key: os.environ.get(key, "")
        for key in ["NO_PROXY", "no_proxy", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]
        if os.environ.get(key)
    }
    raw = ",".join([env_values.get("NO_PROXY", ""), env_values.get("no_proxy", "")])
    tokens = {token.strip().lower() for token in raw.split(",") if token.strip()}
    missing = sorted(host for host in LOCAL_BYPASS_HOSTS if host.lower() not in tokens)
    return {"ok": not missing, "missing": missing, "env": env_values}


def chrome_running() -> bool:
    system = platform.system().lower()
    try:
        if system == "windows":
            result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe"], capture_output=True, text=True, timeout=5)
            return "chrome.exe" in result.stdout.lower()
        for name in LINUX_CHROME_PROCESS_NAMES:
            result = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return True
        return False
    except (OSError, subprocess.SubprocessError):
        return False


def stop_chrome() -> None:
    system = platform.system().lower()
    if system == "windows":
        subprocess.run(["taskkill", "/IM", "chrome.exe", "/T", "/F"], check=False)
    elif system == "darwin":
        subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to quit'], check=False)
        time.sleep(2)
    else:
        for name in LINUX_CHROME_PROCESS_NAMES:
            subprocess.run(["pkill", "-x", name], check=False)


def start_chrome(layout: ChromeLayout) -> None:
    if not layout.chrome_path:
        raise RuntimeError("Google Chrome executable was not found.")
    if platform.system().lower() == "windows":
        subprocess.Popen(layout.launch_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        subprocess.Popen(layout.launch_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def run_command(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=patched_env())
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(args=args, returncode=127, stdout="", stderr=str(exc))
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(args=args, returncode=124, stdout=exc.stdout or "", stderr=exc.stderr or f"command timed out after {timeout}s")


def patched_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("NO_PROXY") or env.get("no_proxy") or ""
    tokens = [token.strip() for token in existing.split(",") if token.strip()]
    for host in ["localhost", "127.0.0.1", "::1"]:
        if host not in tokens:
            tokens.append(host)
    env["NO_PROXY"] = ",".join(tokens)
    env["no_proxy"] = env["NO_PROXY"]
    return env


def agent_browser_args(port: int, prefer_auto: bool = True) -> list[str]:
    if not shutil.which("agent-browser"):
        raise RuntimeError("agent-browser is not on PATH")
    if prefer_auto:
        probe = run_command(["agent-browser", "--auto-connect", "get", "url"], timeout=12)
        if probe.returncode == 0:
            return ["agent-browser", "--auto-connect"]
    if cdp_available(port):
        return ["agent-browser", "--cdp", str(port)]
    return ["agent-browser", "--auto-connect"]


def choose_backend(port: int) -> BrowserBackend:
    if shutil.which("agent-browser"):
        try:
            base = agent_browser_args(port)
            probe = run_command([*base, "get", "url"], timeout=12)
            if probe.returncode == 0:
                return BrowserBackend(name="agent-browser", agent_browser_base=base)
        except RuntimeError:
            pass

    playwright = probe_playwright(port)
    if playwright["ok"]:
        return BrowserBackend(name="playwright")

    raise RuntimeError(
        "No executable browser backend is ready. Tried agent-browser and Playwright CDP; "
        "handoff to the runtime Chrome extension is required."
    )


def probe_agent_browser(port: int) -> dict[str, Any]:
    if not shutil.which("agent-browser"):
        return {"ok": False, "reason": "agent-browser is not on PATH"}
    version = run_command(["agent-browser", "--version"], timeout=10)
    auto = run_command(["agent-browser", "--auto-connect", "get", "url"], timeout=12)
    explicit_ok = False
    explicit_error = ""
    if cdp_available(port):
        explicit = run_command(["agent-browser", "--cdp", str(port), "get", "url"], timeout=12)
        explicit_ok = explicit.returncode == 0
        explicit_error = explicit.stderr.strip() or explicit.stdout.strip()
    return {
        "ok": auto.returncode == 0 or explicit_ok,
        "version": (version.stdout or version.stderr).strip(),
        "auto_connect_ok": auto.returncode == 0,
        "auto_connect_output": (auto.stdout or auto.stderr).strip(),
        "explicit_cdp_ok": explicit_ok,
        "explicit_cdp_output": explicit_error,
    }


def probe_playwright(port: int) -> dict[str, Any]:
    if not shutil.which("node"):
        return {"ok": False, "reason": "node is not on PATH"}
    script = (
        "const {chromium}=require('playwright');"
        f"chromium.connectOverCDP('http://127.0.0.1:{port}')"
        ".then(async b=>{const pages=b.contexts().flatMap(c=>c.pages());"
        "console.log(JSON.stringify({pages:pages.length,url:pages[0]?.url()||null})); await b.close();})"
        ".catch(e=>{console.error(e.message); process.exit(2);});"
    )
    result = run_command(["node", "-e", script], timeout=20)
    return {
        "ok": result.returncode == 0,
        "output": (result.stdout or result.stderr).strip(),
        "reason": None if result.returncode == 0 else "playwright is unavailable or cannot connect over CDP",
    }


def run_playwright_action(port: int, action: str, payload: dict[str, Any] | None = None, timeout: int = 120) -> str:
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    script = r"""
const { chromium } = require('playwright');
const action = process.argv[1];
const payload = JSON.parse(process.argv[2] || '{}');
const chatUrl = 'https://chatgpt.com/';

async function chatPage(browser) {
  const context = browser.contexts()[0] || await browser.newContext();
  let page = context.pages().find((p) => p.url().includes('chatgpt.com'));
  if (!page) page = await context.newPage();
  return page;
}

(async () => {
  const browser = await chromium.connectOverCDP(payload.cdpUrl);
  const page = await chatPage(browser);
  if (action === 'open') {
    await page.goto(chatUrl, { waitUntil: 'domcontentloaded' });
    console.log(page.url());
  } else if (action === 'eval') {
    const value = await page.evaluate(payload.expression);
    console.log(typeof value === 'string' ? value : JSON.stringify(value));
  } else if (action === 'insert-submit') {
    await page.locator('#prompt-textarea').click({ timeout: 20000 });
    await page.evaluate((text) => {
      const el = document.querySelector('#prompt-textarea');
      if (!el) throw new Error('prompt textarea not found');
      el.focus();
      document.execCommand('selectAll', false, null);
      document.execCommand('insertText', false, text);
      el.dispatchEvent(new InputEvent('input', { inputType: 'insertText', data: text, bubbles: true }));
    }, payload.prompt);
    await page.keyboard.press('Enter');
    console.log('submitted');
  } else {
    throw new Error(`unknown action: ${action}`);
  }
  await browser.close();
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(2);
});
"""
    result = run_command(
        ["node", "-e", script, action, payload_json],
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


async def read_cdp_response(ws: Any, response_id: int, timeout: int = 10) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.time()))
        except asyncio.TimeoutError:
            return {}
        msg = json.loads(raw)
        if msg.get("id") == response_id:
            return msg
    return {}


def diagnose(args: argparse.Namespace) -> int:
    layout = default_chrome_layout(args.port)
    if args.restart_chrome and not cdp_available(args.port):
        if chrome_running():
            stop_chrome()
            time.sleep(3)
        start_chrome(layout)
        for _ in range(20):
            if cdp_available(args.port):
                break
            time.sleep(0.5)
    proxy = proxy_bypass_status()
    cdp = cdp_get("/json/version", args.port)
    state = {
        "os": layout.os_name,
        "chrome_path": str(layout.chrome_path) if layout.chrome_path else None,
        "user_data_dir": str(layout.user_data_dir),
        "profile_dir": str(layout.profile_dir),
        "default_profile_exists": layout.profile_dir.exists(),
        "chrome_running": chrome_running(),
        "cdp_port": args.port,
        "cdp_available": bool(cdp),
        "cdp_version": cdp,
        "proxy_bypass": proxy,
        "agent_browser": probe_agent_browser(args.port),
        "playwright_cdp": probe_playwright(args.port) if bool(cdp) else {"ok": False, "reason": "CDP is not available"},
        "chrome_extension": {
            "ok": None,
            "reason": "Shell helper cannot call runtime Chrome connectors; use this as third backend after agent-browser and Playwright diagnostics.",
        },
        "launch_command": layout.launch_args,
    }
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print_human_diagnosis(state)
    return 0 if state["cdp_available"] and state["proxy_bypass"]["ok"] else 2


def print_human_diagnosis(state: dict[str, Any]) -> None:
    print("Chrome Default profile diagnosis")
    print(f"- os: {state['os']}")
    print(f"- chrome: {state['chrome_path'] or 'NOT FOUND'}")
    print(f"- default profile: {state['profile_dir']} ({'exists' if state['default_profile_exists'] else 'missing'})")
    print(f"- chrome running: {state['chrome_running']}")
    print(f"- CDP port {state['cdp_port']}: {'ok' if state['cdp_available'] else 'not listening'}")
    proxy = state["proxy_bypass"]
    print(f"- NO_PROXY loopback: {'ok' if proxy['ok'] else 'missing ' + ','.join(proxy['missing'])}")
    print(f"- agent-browser: {'ok' if state['agent_browser']['ok'] else 'not ready'}")
    print(f"- Playwright CDP: {'ok' if state['playwright_cdp']['ok'] else state['playwright_cdp'].get('reason', 'not ready')}")
    print("- backend order: agent-browser -> Playwright connectOverCDP -> runtime Chrome extension")
    if not state["cdp_available"]:
        print("CDP is not available. Restart Chrome with the launch command below after closing the normal Default profile Chrome:")
        print(" ".join(json.dumps(x) for x in state["launch_command"]))


def ensure_cdp(args: argparse.Namespace) -> ChromeLayout:
    layout = default_chrome_layout(args.port)
    if cdp_available(args.port):
        return layout
    if args.restart_chrome:
        if chrome_running():
            stop_chrome()
            time.sleep(3)
        start_chrome(layout)
        for _ in range(20):
            if cdp_available(args.port):
                return layout
            time.sleep(0.5)
    raise RuntimeError("CDP is not available for the Chrome Default profile. Run diagnose, then restart Chrome with --restart-chrome if allowed.")


def open_chatgpt(args: argparse.Namespace) -> BrowserBackend:
    ensure_cdp(args)
    backend = choose_backend(args.port)
    if backend.name == "agent-browser":
        if not backend.agent_browser_base:
            raise RuntimeError("agent-browser backend selected without command prefix")
        for command in [
            [*backend.agent_browser_base, "tab", "new"],
            [*backend.agent_browser_base, "open", CHATGPT_URL],
        ]:
            result = run_command(command, timeout=30)
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout).strip())
    elif backend.name == "playwright":
        run_playwright_action(args.port, "open", {"cdpUrl": f"http://127.0.0.1:{args.port}"})
    return backend


def backend_eval(args: argparse.Namespace, backend: BrowserBackend, expression: str) -> str:
    if backend.name == "agent-browser":
        if not backend.agent_browser_base:
            raise RuntimeError("agent-browser backend selected without command prefix")
        result = run_command([*backend.agent_browser_base, "eval", expression], timeout=30)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip())
        return result.stdout.strip()
    if backend.name == "playwright":
        return run_playwright_action(
            args.port,
            "eval",
            {"cdpUrl": f"http://127.0.0.1:{args.port}", "expression": expression},
            timeout=30,
        )
    raise RuntimeError(f"Unsupported backend: {backend.name}")


def insert_prompt(args: argparse.Namespace, backend: BrowserBackend, prompt: str) -> None:
    if backend.name == "playwright":
        run_playwright_action(
            args.port,
            "insert-submit",
            {"cdpUrl": f"http://127.0.0.1:{args.port}", "prompt": prompt},
            timeout=120,
        )
        return
    if not backend.agent_browser_base:
        raise RuntimeError("agent-browser backend selected without command prefix")
    click = run_command([*backend.agent_browser_base, "click", "#prompt-textarea"], timeout=20)
    if click.returncode != 0:
        raise RuntimeError((click.stderr or click.stdout).strip())
    expression = (
        "(()=>{"
        f"const text={json.dumps(prompt)};"
        "const el=document.querySelector('#prompt-textarea');"
        "if(!el) return 'prompt textarea not found';"
        "el.focus();"
        "document.execCommand('selectAll', false, null);"
        "document.execCommand('insertText', false, text);"
        "el.dispatchEvent(new InputEvent('input',{inputType:'insertText',data:text,bubbles:true}));"
        "return 'inserted';"
        "})()"
    )
    inserted = run_command([*backend.agent_browser_base, "eval", expression], timeout=60)
    if inserted.returncode != 0 or "inserted" not in (inserted.stdout or ""):
        raise RuntimeError((inserted.stderr or inserted.stdout).strip())
    sent = run_command([*backend.agent_browser_base, "press", "Enter"], timeout=20)
    if sent.returncode != 0:
        raise RuntimeError((sent.stderr or sent.stdout).strip())


ASSISTANT_STATE_EXPRESSION = (
    "(()=>{"
    "const els=[...document.querySelectorAll('[data-message-author-role=\"assistant\"]')];"
    "const text=els.length?els[els.length-1].innerText:'';"
    "const live=[...document.querySelectorAll('button,[role=\"status\"],[aria-live]')].map(el=>el.innerText||'').join('\\n');"
    "const busy=document.querySelectorAll('[aria-busy=\"true\"]').length>0 || /思考中|停止|今すぐ回答|Thinking|Stop|Stop generating|Respond now|Searching/.test(live);"
    "return JSON.stringify({count:els.length,text,busy});"
    "})()"
)


def parse_state(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
    return {"count": 0, "text": "", "busy": False}


def wait_state_path(port: int) -> Path:
    return Path(tempfile.gettempdir()) / f"devkit-chatgpt-runner-{port}.json"


def save_wait_baseline(port: int, baseline: dict[str, Any]) -> None:
    wait_state_path(port).write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")


def load_wait_baseline(port: int) -> dict[str, Any] | None:
    path = wait_state_path(port)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def run_gpt_pro(args: argparse.Namespace) -> int:
    backend = open_chatgpt(args)
    if args.prompt:
        baseline = parse_state(backend_eval(args, backend, ASSISTANT_STATE_EXPRESSION))
        insert_prompt(args, backend, args.prompt)
        save_wait_baseline(args.port, baseline)
    print("ChatGPT is open in Chrome Default profile.")
    print(f"Backend: {backend.name}")
    if args.prompt:
        print("Prompt was submitted. Use `wait-gpt-pro` to poll the latest assistant reply.")
    return 0


def run_deep_research(args: argparse.Namespace) -> int:
    backend = open_chatgpt(args)
    select = (
        "(function(){"
        "const labels=['Deep research','Deep Research','ディープリサーチ'];"
        "const nodes=[...document.querySelectorAll('a,button,[role=\"menuitem\"]')];"
        "const node=nodes.find(n=>labels.some(x=>(n.innerText||n.textContent||'').includes(x)));"
        "if(node){node.click(); return 'clicked deep research';}"
        "return 'deep research control not found; choose it manually in the Default profile Chrome';"
        "})()"
    )
    selected = backend_eval(args, backend, select)
    print(selected)
    if "clicked deep research" not in selected:
        return 2
    if args.prompt:
        insert_prompt(args, backend, args.prompt)
        print("Deep Research prompt was submitted. Use `extract-deep-research` after completion.")
    return 0


def wait_gpt_pro(args: argparse.Namespace) -> int:
    ensure_cdp(args)
    backend = choose_backend(args.port)
    baseline = load_wait_baseline(args.port)
    if baseline is None:
        baseline = parse_state(backend_eval(args, backend, ASSISTANT_STATE_EXPRESSION))
    previous = ""
    stable = 0
    deadline = time.time() + args.timeout_minutes * 60
    while time.time() < deadline:
        state = parse_state(backend_eval(args, backend, ASSISTANT_STATE_EXPRESSION))
        text = str(state.get("text") or "")
        changed = int(state.get("count") or 0) > int(baseline.get("count") or 0) or text != str(baseline.get("text") or "")
        busy = bool(state.get("busy"))
        if changed and text and not busy and text == previous:
            stable += 1
        else:
            stable = 0
        if stable >= 2:
            print(text)
            return 0
        previous = text
        time.sleep(args.interval)
    print("Timed out waiting for a stable ChatGPT Pro response.", file=sys.stderr)
    return 2


def extract_deep_research(args: argparse.Namespace) -> int:
    data = cdp_get("/json", args.port)
    if not isinstance(data, list):
        print("CDP target list is unavailable.", file=sys.stderr)
        return 2
    targets = [t for t in data if "deep_research" in t.get("url", "") or "oaiusercontent" in t.get("url", "")]
    if not targets:
        print("Deep Research iframe target was not found. Check the Chrome tab visually or retry after the report appears.", file=sys.stderr)
        return 2
    try:
        import websockets  # type: ignore
    except ImportError:
        print("Python package `websockets` is required to extract sandboxed Deep Research iframe text.", file=sys.stderr)
        return 3

    async def extract_from_target(target: dict[str, Any]) -> str:
        ws_url = target["webSocketDebuggerUrl"]
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            contexts: list[dict[str, Any]] = []
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=3)
                except asyncio.TimeoutError:
                    break
                msg = json.loads(raw)
                if msg.get("method") == "Runtime.executionContextCreated":
                    contexts.append(msg["params"]["context"])
            for index, ctx in enumerate(contexts, start=10):
                await ws.send(
                    json.dumps(
                        {
                            "id": index,
                            "method": "Runtime.evaluate",
                            "params": {
                                "expression": 'document.querySelector("[class*=\\"report\\"]")?.innerText || document.body.innerText',
                                "contextId": ctx["id"],
                                "returnByValue": True,
                            },
                        }
                    )
                )
                response = await read_cdp_response(ws, index, timeout=10)
                value = response.get("result", {}).get("result", {}).get("value", "")
                if isinstance(value, str) and len(value.strip()) > 200:
                    return value.strip()
        return ""

    async def extract() -> str:
        for target in targets:
            try:
                report = await extract_from_target(target)
            except Exception:
                continue
            if report:
                return report
        return ""

    report = asyncio.run(extract())
    if not report:
        print("Could not extract Deep Research report text.", file=sys.stderr)
        return 2
    print(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ChatGPT Pro / Deep Research through Chrome Default profile.")
    parser.add_argument("--port", type=int, default=9222, help="Chrome DevTools Protocol port.")
    parser.add_argument("--restart-chrome", action="store_true", help="Close Chrome and relaunch the Default profile with CDP if needed.")
    parser.add_argument("--json", action="store_true", help="Emit JSON for diagnose.")
    sub = parser.add_subparsers(dest="command", required=True)
    diagnose_parser = sub.add_parser("diagnose")
    diagnose_parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Emit JSON for diagnose.")
    gpt = sub.add_parser("gpt-pro")
    gpt.add_argument("prompt", nargs="?", default="")
    dr = sub.add_parser("deep-research")
    dr.add_argument("prompt", nargs="?", default="")
    wait = sub.add_parser("wait-gpt-pro")
    wait.add_argument("--timeout-minutes", type=int, default=60)
    wait.add_argument("--interval", type=int, default=30)
    sub.add_parser("extract-deep-research")
    return parser


def main() -> int:
    os.environ.update(patched_env())
    args = build_parser().parse_args()
    try:
        if args.command == "diagnose":
            return diagnose(args)
        if args.command == "gpt-pro":
            return run_gpt_pro(args)
        if args.command == "deep-research":
            return run_deep_research(args)
        if args.command == "wait-gpt-pro":
            return wait_gpt_pro(args)
        if args.command == "extract-deep-research":
            return extract_deep_research(args)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
