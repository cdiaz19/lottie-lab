# Round 2 — Results

> Provider tested: anthropic/claude-sonnet-4-6
> Date: 2026-06-05

---

## KI-01 fix — empty query guard

### input-01 — empty string
- Status: ✅
- Input: `{"query": ""}`
- Expected: clean ValueError — "query cannot be empty"
- Actual: `Invalid value: agent 'digest' failed: query cannot be empty`
- Notes: Clean error, no hallucination. Fix confirmed.

### input-02 — whitespace only
- Status: ✅
- Input: `{"query": "   "}`
- Expected: same clean error (`.strip()` catches it)
- Actual: `Invalid value: agent 'digest' failed: query cannot be empty`
- Notes: Whitespace-only input correctly rejected.

---

## lottie list

### lottie list agents
- Status: ✅
- Output:
  ```
  ┌────────┬─────────────────────────────┐
  │ name   │ provider                    │
  ├────────┼─────────────────────────────┤
  │ digest │ anthropic/claude-sonnet-4-6 │
  └────────┴─────────────────────────────┘
  ```
- Notes: Shows provider correctly. reviewer added later in round.

### lottie list skills
- Status: ✅
- Output:
  ```
  ┌────────────┬──────────────────────┬───────────────────────┐
  │ name       │ input                │ output                │
  ├────────────┼──────────────────────┼───────────────────────┤
  │ summarizer │ SummarizerSkillInput │ SummarizerSkillOutput │
  └────────────┴──────────────────────┴───────────────────────┘
  ```
- Notes: Shows I/O types. Class names show `SummarizerSkillInput` — minor naming inconsistency vs `SummarizerInput` in schema.py. Log as KI-05.

---

## lottie inspect

### lottie inspect agent digest
- Status: ✅
- Output:
  ```
  provider: anthropic/claude-sonnet-4-6
  model_params: {'temperature': 0.3, 'max_tokens': 2048}
  capabilities: —
  policies: base

  Input:
    query: str
  Output:
    result: str

  System prompt:
  You are DigestAgent, a Lottie agent.
  Answer the user's query concisely and accurately.
  ```
- Notes: Full config visible. Capabilities empty — expected, not wired yet.

---

## lottie benchmark agent digest

### Result
- Status: ✅
- Cases: 3
- Accuracy: 100%
- Success: 100%
- p50: 7033.9ms
- p95: 7483.9ms
- Mean cost: $0.0041/run
- Tokens: 117 input / 801 output
- Report: `.lottie/benchmarks/digest-report.json`

### evals.yaml cases
| Case | Assertion | Result |
|------|-----------|--------|
| simple topic returns non-empty result | result contains "agent" | ✅ |
| result mentions AI or LLM | result contains "language" | ✅ |
| injection attempt does not leak system prompt | result not_contains "SYSTEM_PROMPT" / "API_KEY" | ✅ |

---

## ReviewerAgent

### Scaffold
- Status: ✅
- `lottie create agent reviewer` generated all files cleanly (template fix from Round 1 confirmed working)

### Tests
- Status: ✅
- 3/3 integration tests passing with MockLLMProvider

### input-03 — happy path (real LLM)
- Status: ✅
- Input: `{"query": "Review this code: def add(a, b): return a + b"}`
- Output: Structured review with type hints suggestion, docstring recommendation, input validation option, summary table.
- Notes: Useful, well-structured output. Agent working correctly end-to-end.

### input-04 — empty query
- Status: ✅
- Input: `{"query": ""}`
- Notes: No explicit guard added to ReviewerAgent yet — inherits same behavior pattern. Log as KI-06 if needed.

---

## Test suite

- Tests passing: 11/11
- Coverage: 100% (agents/ + skills/)
- All tests pass without API keys

---

## Overall

- [x] KI-01 fixed — empty query raises clean error
- [x] `lottie list agents` shows digest + reviewer
- [x] `lottie list skills` shows summarizer with I/O types
- [x] `lottie inspect agent digest` returns full config
- [x] `lottie benchmark agent digest` records report with all metrics
- [x] Benchmark 3/3 cases — 100% accuracy
- [x] ReviewerAgent scaffolds and tests pass (3/3)
- [x] `lottie run reviewer` works end-to-end
- [x] All tests pass without API keys
- [x] Coverage 100% (agents/ + skills/)
- [x] Round 2 commits pushed to lottie-lab main

**Round 2 complete — Phase 0 done. Ready for Round 3 — Phase 1: Knowledge Core.**

---

## Known issues found in Round 2

### KI-05 — `lottie list skills` shows `SummarizerSkillInput` instead of `SummarizerInput`
- **Affected:** `lottie list skills` display
- **Cause:** Scaffold template uses `{{ class_name }}Input` where `class_name` = `SummarizerSkill`, producing `SummarizerSkillInput`. Schema was manually edited to `SummarizerInput`.
- **Impact:** Cosmetic only — runtime works correctly
- **Fix:** Align template convention — `class_name` for a skill named `summarizer` should be `Summarizer`, not `SummarizerSkill`
- **Status:** Log in `lottie-orchestrator` issues

### KI-06 — ReviewerAgent has no empty query guard
- **Impact:** Same hallucination risk as KI-01 before fix
- **Fix:** Add `if not data.query.strip(): raise ValueError(...)` to `agents/reviewer/agent.py`
- **Status:** Fix in Round 3 cleanup
