# lottie-lab 🐶
> Public testing ground for [Lottie Orchestrator](https://github.com/cdiaz19/lottie-orchestrator) — a provider-agnostic multi-agent AI framework.

Built in the open. Every round tests a new phase of the framework against real inputs, real providers, and honest results.

---

## What is Lottie?

Lottie lets you define **Agents** (LLM-backed units that reason and decide) and **Skills** (stateless, deterministic capabilities), then wire them together with one CLI. Swap Claude for GPT-4o with a single config change - no code changes, ever.

```bash
lottie create agent digest          # scaffold a new agent
lottie run digest --input '{...}'   # run it against any provider
lottie benchmark agent digest       # record latency, cost, accuracy
```

---

## Rounds

Each round maps to a Lottie phase. A round doesn't close until every item on its checklist is signed off.

| Round | Phase | Focus | Status |
|-------|-------|-------|--------|
| [Round 1](rounds/round-1-foundations/) | Phase 0 | Foundations - CLI, BaseAgent, BaseSkill, first agent end-to-end | 🔄 In progress |
| Round 2 | Phase 1 | Knowledge — document ingest, RAG pipeline, knowledge graph | ⏳ Pending |
| Round 3 | Phase 2 | Multi-agent mesh — LangGraph, supervisor - workers, parallel runs | ⏳ Pending |
| Round 4 | Phase 3 | Governance — audit trail, policy engine, security layer | ⏳ Pending |
| Round 5 | Phase 4 | Integration — MCP server, OpenAI-compat API | ⏳ Pending |

---

## Round 1 — Foundations

**Agent:** `DigestAgent` — takes a topic or block of text, calls `SummarizerSkill`, returns a structured digest: summary + key points + follow-up questions.

**Skill:** `SummarizerSkill` — stateless, typed I/O, wraps an LLM call to condense text.

**Test inputs:**

| Input | What it tests |
|-------|--------------|
| `input-01-simple-topic.json` | Happy path — short topic string |
| `input-02-long-text.json` | Real article — multi-paragraph text |
| `input-03-empty-topic.json` | Edge case — empty string input |
| `input-04-very-long-text.json` | Stress — input near token limit |
| `input-05-special-chars.json` | Edge case — HTML, quotes, ampersands |
| `input-06-injection-attempt.json` | Security — prompt injection attempt |

Results logged in [`rounds/round-1-foundations/results.md`](rounds/round-1-foundations/results.md).

---

## How to run locally

Soon - Note: lottie-orchestrator will be published to PyPI with the v0.1.0 tag.

---

## Providers tested

| Provider | Model | Notes |
|----------|-------|-------|
| Anthropic | claude-sonnet-4-6 | Default |
| OpenAI | gpt-4o | Comparison runs via `--compare` |

---

## Related

- [`lottie-orchestrator`](https://github.com/cdiaz19/lottie-orchestrator) — the framework this repo tests
- Built by [@cdiaz19](https://github.com/cdiaz19) · [@Stardew-Global-Holdings](https://github.com/Stardew-Global-Holdings)
[#buildinpublic](https://twitter.com/search?q=%23buildinpublic)