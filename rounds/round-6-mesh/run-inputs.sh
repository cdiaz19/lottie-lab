#!/usr/bin/env bash
# Round-6 input-case runner. Runs each inputs/input-*.json against the lab CLI
# (cwd = lab; editor mesh lives here) on Mock providers (keys unset), writes raw
# output to outputs/<name>.out.json, checks _expect_contains. Non-zero on any miss.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
OUT="$HERE/outputs"
unset ANTHROPIC_API_KEY OPENAI_API_KEY
mkdir -p "$OUT"
fail=0

for f in "$HERE"/inputs/input-*.json; do
  name="$(basename "$f" .json)"
  argv=()
  while IFS= read -r line; do argv+=("$line"); done < <(python3 -c "
import json,sys
for a in json.load(open(sys.argv[1]))['argv']:
    print(a)
" "$f")

  out="$( cd "$LAB" && lottie "${argv[@]}" 2>&1 | grep -vE 'LiteLLM|botocore' )"
  printf '%s\n' "$out" > "$OUT/$name.out.json"

  miss=0
  while IFS= read -r sub; do
    [ -z "$sub" ] && continue
    grep -qF -- "$sub" "$OUT/$name.out.json" || { echo "  MISS substring: $sub"; miss=1; }
  done < <(python3 -c "import json,sys;[print(s) for s in json.load(open(sys.argv[1])).get('_expect_contains',[])]" "$f")

  if [ "$miss" = 0 ]; then echo "PASS $name"; else echo "FAIL $name"; fail=1; fi
done
exit $fail
