#!/usr/bin/env bash
# Documania — Claude Code cloud oturumunun açılış kurulumu (SessionStart kancası, .claude/settings.json).
#
# Cloud'da (Linux) çalışır; yerel Windows makinesinde (Git Bash) hiçbir şey yapmadan çıkar.
# Python 3.12 ortamını `uv.lock`'tan birebir kurar (`.venv`), Task Master CLI'yi kurar ve
# `.venv/bin`'i oturumun PATH'ine ekler: pencere `python`, `pytest`, `ruff`, `alembic`'i doğrudan çağırır.
set -euo pipefail

case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) exit 0 ;;
esac

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}"

command -v uv >/dev/null 2>&1 || python3 -m pip install --quiet uv
uv sync --frozen --extra dev --python 3.12 --quiet

command -v task-master >/dev/null 2>&1 || npm install --global --silent task-master-ai >/dev/null

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export VIRTUAL_ENV=\"$PWD/.venv\""
    echo "export PATH=\"$PWD/.venv/bin:\$PATH\""
  } >> "$CLAUDE_ENV_FILE"
fi
