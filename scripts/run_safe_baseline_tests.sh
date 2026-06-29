#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -x "/opt/genesi/.venv/bin/python" ]]; then
  PYTHON="/opt/genesi/.venv/bin/python"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
else
  PYTHON="python"
fi

cd "$ROOT_DIR"

echo "== Genesi safe baseline =="
echo "root=$ROOT_DIR"
echo "python=$PYTHON"

"$PYTHON" -m pytest tests/test_group_controls.py -q
"$PYTHON" -m pytest tests/test_admin_fallback.py -q
"$PYTHON" -m pytest tests/test_telegram_operational.py -q
"$PYTHON" -m pytest tests/test_whatsapp_operational.py -q
"$PYTHON" -m pytest tests/test_operational_ingest_filter.py -q

"$PYTHON" -m py_compile \
  core/group_controls.py \
  api/admin/automation.py \
  api/admin_fallback.py \
  core/fallback_engine.py \
  core/telegram_bot.py \
  core/operational_memory/telegram_operational.py \
  core/operational_memory/whatsapp_operational.py

echo "== Genesi safe baseline OK =="
