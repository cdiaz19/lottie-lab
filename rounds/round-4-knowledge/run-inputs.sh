#!/usr/bin/env bash
# Round-4 input-case runner.
# Executes each inputs/input-*.json against its CLI surface on Mock providers
# (API keys unset), writes raw output to outputs/<name>.out.json, and checks
# the declared _expect_contains / _expect_json_keys.  Exit non-zero on any miss.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ORCH="/Users/cdiaz19/Documents/trae_projects/lottie-orchestrator"
FIXTURE="$HERE/inputs/fixture"
OUT="$HERE/outputs"
unset ANTHROPIC_API_KEY OPENAI_API_KEY
mkdir -p "$OUT"
fail=0

PY() { python3 -c "$1" "$@"; }

for f in "$HERE"/inputs/input-*.json; do
  name="$(basename "$f" .json)"
  uses_tmp="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('uses_tmp_root',False))" "$f")"
  notstored="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('_expect_not_stored',False))" "$f")"

  # Build argv array (portable; substitute {FIXTURE})
  argv=()
  while IFS= read -r line; do argv+=("$line"); done < <(python3 -c "
import json,sys
for a in json.load(open(sys.argv[1]))['argv']:
    print(a.replace('{FIXTURE}', sys.argv[2]))
" "$f" "$FIXTURE")

  TMPR=""
  if [ "$uses_tmp" = "True" ]; then TMPR="$(mktemp -d)"; argv+=(--root "$TMPR"); fi

  out="$( cd "$ORCH" && lottie "${argv[@]}" 2>&1 | grep -vE 'LiteLLM|botocore' )"
  printf '%s\n' "$out" > "$OUT/$name.out.json"

  miss=0
  while IFS= read -r sub; do
    [ -z "$sub" ] && continue
    grep -qF -- "$sub" "$OUT/$name.out.json" || { echo "  MISS substring: $sub"; miss=1; }
  done < <(python3 -c "import json,sys;[print(s) for s in json.load(open(sys.argv[1])).get('_expect_contains',[])]" "$f")
  while IFS= read -r key; do
    [ -z "$key" ] && continue
    grep -qF -- "\"$key\"" "$OUT/$name.out.json" || { echo "  MISS json key: $key"; miss=1; }
  done < <(python3 -c "import json,sys;[print(s) for s in json.load(open(sys.argv[1])).get('_expect_json_keys',[])]" "$f")

  if [ "$notstored" = "True" ] && [ -n "$TMPR" ]; then
    if find "$TMPR/knowledge/draft" -name '*.md' 2>/dev/null | grep -q .; then
      echo "  MISS: injection source was stored under draft/"; miss=1
    fi
  fi
  [ -n "$TMPR" ] && rm -rf "$TMPR"

  if [ "$miss" = 0 ]; then echo "PASS $name"; else echo "FAIL $name"; fail=1; fi
done
exit $fail
