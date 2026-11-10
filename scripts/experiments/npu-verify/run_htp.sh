#!/usr/bin/env bash
set -euo pipefail
BASE=/srv/vision-data/tools/npu-verify
mkdir -p "$BASE/tmp" "$BASE/cache" "$BASE/logs"
export TMPDIR="$BASE/tmp"
export XDG_CACHE_HOME="$BASE/cache"
export PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH="$BASE/pkgroot/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export ADSP_LIBRARY_PATH="$BASE/pkgroot/usr/share/qcom/qcs8300/Qualcomm/QCS8300-RIDE/dsp/cdsp;/usr/lib/dsp/cdsp"
cd "$BASE/logs"
exec "$BASE/.venv/bin/python" -B "$BASE/verify_htp.py"
