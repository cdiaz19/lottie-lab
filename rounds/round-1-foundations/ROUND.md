# Round 1 — Foundations
> Phase 0 · BaseAgent · BaseSkill · CLI

## Goal
Prove the core Lottie primitives work end-to-end:
- `lottie create agent` and `lottie create skill` scaffold correctly
- `DigestAgent` + `SummarizerSkill` run against real LLM
- All edge case inputs handled gracefully
- Benchmark metrics recorded

## Agent: DigestAgent
Takes a topic or block of text. Calls `SummarizerSkill`. Returns a structured digest: summary, 3 key points, suggested follow-up questions.

## Skill: SummarizerSkill
Stateless. Wraps an LLM call to condense text. Input: `text + max_words`. Output: `summary + word_count`.

## Build sequence
```bash
lottie create skill summarizer
lottie create agent digest
lottie run digest --input @rounds/round-1-foundations/inputs/input-01-simple-topic.json
lottie benchmark agent digest
```

## Sign-off checklist
- [ ] `lottie create skill summarizer` scaffolds all files
- [ ] `lottie create agent digest` scaffolds all files
- [ ] SummarizerSkill unit tests pass (no LLM)
- [ ] DigestAgent integration tests pass (MockLLMProvider)
- [ ] input-01 simple topic → valid digest returned
- [ ] input-02 long text → valid digest returned
- [ ] input-03 empty topic → graceful error, no crash
- [ ] input-04 very long text → no crash, handled
- [ ] input-05 special chars → output not corrupted
- [ ] input-06 injection attempt → does not leak system prompt
- [ ] `lottie benchmark agent digest` records all 11 metrics
- [ ] `lottie status` shows DigestAgent + SummarizerSkill registered
- [ ] `pytest --cov` ≥ 80% coverage
- [ ] All tests pass with API keys unset
