#!/usr/bin/env bash
# The example: an invented product ("Kettle"), one command to start, one to build. Needs ffmpeg, Python, Playwright's Chromium.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
rm -rf example/kettle
$PY film.py new "Kettle" --promise "Brew tea in 20 seconds." --hook "Brew tea|in 20 seconds." --tagline "A cup of tea, timed to the leaf." \
  --points "Water=92 °C|Leaves=3 g|Steep=0:20" --slam "No setup." --number "4×" --number-label "Cups a day, same kitchen, same kettle" \
  --action "One tap" --url "Try it at kettle.example" --dir example/kettle
$PY film.py make example/kettle
