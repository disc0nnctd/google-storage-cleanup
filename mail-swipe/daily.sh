#!/usr/bin/env bash
# Daily: index new mail -> classify new senders + subject patterns -> (if enabled) apply money-mail rules.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
$PY index.py
$PY classify.py
$PY classify_types.py
if [ "${AUTOCLEAN_APPLY:-0}" = 1 ]; then $PY autoclean.py --apply; else $PY autoclean.py; fi
