#!/usr/bin/env bash
# Run every lab round that can be run, and fail loudly if any round is SKIPPED.
#
# Why this exists: the ad-hoc `for r in round-a round-b ...` sweeps named rounds by hand,
# and a round left off the list looked exactly like a round that passed. That is how
# R28/R33 stayed broken through a merge, and how R8 sat failing across a whole epic.
# Here a round that cannot be run is reported as a FAILURE, not as silence.
#
# A round is runnable if it has run-inputs.sh (authoritative — it sets up whatever env the
# round needs, and exits non-zero on any miss) or a _*.py driver that prints a RESULT line.
set -uo pipefail
cd "$(dirname "$0")"

PY=${PY:-.venv/bin/python}
# Several round harnesses shell out to `lottie` and assume an activated venv. Put the
# venv on PATH so a round never fails for the harness rather than for the code.
export PATH="$(cd "$(dirname "$PY")" && pwd):$PATH"
fail=0
ran=0
manual=()

for dir in rounds/*/; do
  name=$(basename "$dir")
  harness="$dir/run-inputs.sh"
  driver=$(find "$dir" -maxdepth 1 -name '_*.py' | head -1)

  if [[ -f "$harness" ]]; then
    out=$(bash "$harness" 2>&1)
    code=$?
    line=$(grep -E '^RESULT' <<<"$out" | tail -1)
    if [[ -z "$line" ]]; then
      passes=$(grep -ciE '^PASS' <<<"$out")
      fails=$(grep -ciE '^FAIL' <<<"$out")
      line="RESULT: ${passes} pass / ${fails} fail (exit $code)"
    fi
    [[ $code -ne 0 ]] && fail=1
  elif [[ -n "$driver" ]]; then
    out=$($PY "$driver" 2>&1)
    line=$(grep -E '^RESULT' <<<"$out" | tail -1)
    if [[ -z "$line" ]]; then
      line="RESULT: NO RESULT LINE — the driver crashed"
      fail=1
      printf '%s\n' "$out" | tail -20
    elif grep -qi 'fail' <<<"$line"; then
      fail=1
    fi
  else
    # Rounds 1-3 predate the driver convention and were validated by hand. They are
    # named here so "not run" is a stated fact rather than an omission.
    manual+=("$name")
    continue
  fi

  printf '%-32s %s\n' "$name" "$line"
  ran=$((ran + 1))
done

echo "---"
echo "rounds run: $ran"
if ((${#manual[@]})); then
  echo "manual rounds (no automated harness, validated by hand when written):"
  printf '  %s\n' "${manual[@]}"
fi
if [[ $fail -eq 0 ]]; then echo "ALL GREEN"; else echo "FAILURES PRESENT"; fi
exit $fail
