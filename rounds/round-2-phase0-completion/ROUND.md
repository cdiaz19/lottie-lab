# Round 2 — Phase 0 Completion
> CLI Registry · Benchmark · KI-01 Fix · Second Agent

## Goal
Prove the remaining Phase 0 CLI commands work end-to-end and close the known issues from Round 1 before opening Phase 1 (Knowledge Core).

## What's being tested

### 1. KI-01 fix — empty query guard
Add validation to `DigestAgent._execute` and confirm the empty input now fails with a clean error instead of hallucinating.

### 2. `lottie list` — registry commands
- `lottie list agents` — shows DigestAgent with provider, version, last-run
- `lottie list skills` — shows SummarizerSkill with I/O types

### 3. `lottie inspect` — full agent/skill detail
- `lottie inspect agent digest` — config, schema, prompts, performance history
- `lottie inspect skill summarizer`

### 4. `lottie benchmark` — performance recording
- `lottie benchmark agent digest` — runs eval suite, records 11 metrics to `.lottie/benchmarks/digest.jsonl`
- Verify JSONL contains: `agent_name`, `provider`, `timestamp`, `latency_p50_ms`, `latency_p95_ms`, `input_tokens`, `output_tokens`, `cost_usd`, `accuracy_pct`, `retry_rate`, `version`

### 5. Second agent — `ReviewerAgent`
Create a second agent to verify the registry handles multiple agents correctly.
- `lottie create agent reviewer`
- `lottie list agents` should show both `digest` and `reviewer`
- Tests use MockLLMProvider

## Build sequence

```bash
# Fix KI-01
# Edit agents/digest/agent.py — add empty query guard

# Verify fix
lottie run digest --input '{"query": ""}'
# expect: clean error, not hallucination

# Second agent
lottie create agent reviewer
pytest agents/reviewer/ -v

# Registry commands
lottie list agents
lottie list skills
lottie inspect agent digest
lottie inspect skill summarizer

# Benchmark (once implemented in lottie-orchestrator)
lottie benchmark agent digest
cat .lottie/benchmarks/digest.jsonl

# Full test suite
pytest skills/ agents/ -v
pytest --cov=agents --cov=skills --cov-report=term-missing
```

## Sign-off checklist

- [ ] KI-01 fixed — empty query raises clean error
- [ ] `lottie list agents` shows digest + reviewer with provider info
- [ ] `lottie list skills` shows summarizer with I/O types
- [ ] `lottie inspect agent digest` returns full config
- [ ] `lottie inspect skill summarizer` returns full config
- [ ] `lottie benchmark agent digest` records JSONL with all 11 metrics
- [ ] JSONL `version` field matches current git commit hash
- [ ] `lottie create agent reviewer` scaffolds all files cleanly
- [ ] ReviewerAgent integration tests pass (MockLLMProvider)
- [ ] `lottie run reviewer` works end-to-end
- [ ] All tests pass without API keys
- [ ] Coverage ≥ 80% (agents/ + skills/)
- [ ] Round 2 commits pushed to lottie-lab main

**All 13 checked = Phase 0 complete. Signal ready → Round 3 opens (Phase 1: Knowledge Core).**
