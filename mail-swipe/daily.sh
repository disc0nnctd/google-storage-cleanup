#!/usr/bin/env bash
# Daily: index new mail -> classify new senders + subject patterns -> (if enabled) apply money-mail rules.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
$PY index.py
$PY classify.py
$PY classify_types.py --everyone
$PY jury.py
$PY autoclean.py
