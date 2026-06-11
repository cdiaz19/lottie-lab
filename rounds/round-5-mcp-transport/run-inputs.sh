#!/usr/bin/env bash
# Round-5 input-case runner.
# Drives each inputs/input-*.json through the MCP in-memory client
# (_mcp_driver.py) against build_mcp_server(LAB_ROOT) on a mocked provider
# (API keys unset). Writes raw output to outputs/<name>.out.json and checks
# the declared _expect_* assertions. Exit non-zero on any miss.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
PY="$LAB/.venv/bin/python"
OUT="$HERE/outputs"
export LAB_ROOT="$LAB"
unset ANTHROPIC_API_KEY OPENAI_API_KEY
mkdir -p "$OUT"
fail=0

# Run from a throwaway cwd so the agent benchmark sink (.lottie/) lands in tmp,
# not in the round folder. All paths the driver touches are absolute.
RUNCWD="$(mktemp -d)"
trap 'rm -rf "$RUNCWD"' EXIT

for f in "$HERE"/inputs/input-*.json; do
  name="$(basename "$f" .json)"
  if ( cd "$RUNCWD" && "$PY" "$HERE/_mcp_driver.py" "$f" ) > "$OUT/$name.out.json" 2> "$OUT/$name.err.raw"; then
    # keep only real diagnostics (drop LiteLLM/botocore import warnings)
    grep -vE 'LiteLLM|botocore|not listed, no validation' "$OUT/$name.err.raw" > "$OUT/$name.err"
    rm -f "$OUT/$name.err.raw"
    [ -s "$OUT/$name.err" ] || rm -f "$OUT/$name.err"
    echo "PASS $name"
  else
    echo "FAIL $name"; grep -vE 'LiteLLM|botocore|not listed, no validation' "$OUT/$name.err.raw" 2>/dev/null
    mv -f "$OUT/$name.err.raw" "$OUT/$name.err" 2>/dev/null
    fail=1
  fi
done
exit $fail
