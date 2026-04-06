#!/bin/sh
set -eu

REPO_ROOT="C:/Users/murak/repos/devkit"
CONFIG_PATH="$REPO_ROOT/.devkit/repo-maintainer.toml"

find_runner() {
  if [ -n "${DEVKIT_SOURCE_ROOT:-}" ] && [ -f "$DEVKIT_SOURCE_ROOT/plugins/devkit/scripts/repo_maintainer.py" ]; then
    printf '%s\n' "$DEVKIT_SOURCE_ROOT/plugins/devkit/scripts/repo_maintainer.py"
    return 0
  fi
  for candidate in \
    "$HOME/.codex/devkit/source/plugins/devkit/scripts/repo_maintainer.py" \
    "$HOME/.config/opencode/devkit/source/plugins/devkit/scripts/repo_maintainer.py" \
    "$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts/repo_maintainer.py"
  do
    if [ -f "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  printf 'PYTHON_NOT_FOUND\n' >&2
  exit 1
fi

RUNNER_PATH="$(find_runner)" || {
  printf 'REPO_MAINTAINER_RUNNER_NOT_FOUND\n' >&2
  exit 1
}

exec "$PYTHON_BIN" "$RUNNER_PATH" run --repo "$REPO_ROOT" --config "$CONFIG_PATH" "$@"
