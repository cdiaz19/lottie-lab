# lottie-lab 🐶
> Public testing ground for [Lottie Orchestrator](https://github.com/cdiaz19/lottie-orchestrator) — a provider-agnostic multi-agent AI framework.

Built in the open. Every round tests a new phase of the framework against real inputs, real providers, and honest results.

---

## What is Lottie?

Lottie lets you define **Agents** (LLM-backed units that reason and decide) and **Skills** (stateless, deterministic capabilities), then wire them together with one CLI. Swap Claude for GPT-4o with a single config change — no code changes, ever.

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
| [Round 1](rounds/round-1-foundations/) | Phase 0 | Foundations — CLI, BaseAgent, BaseSkill, first agent end-to-end | Complete |
| [Round 2](rounds/round-2-phase0-completion/) | Phase 0 | Registry, benchmark, KI-01 fix, second agent | Complete |
| Round 3 | Phase 1 | Knowledge — document ingest, RAG pipeline, knowledge graph | ⏳ Pending |
| Round 4 | Phase 2 | Multi-agent mesh — LangGraph, supervisor → workers, parallel runs | ⏳ Pending |
| Round 5 | Phase 3 | Governance — audit trail, policy engine, security layer | ⏳ Pending |
| Round 6 | Phase 4 | Integration — MCP server, OpenAI-compat API | ⏳ Pending |

---

## Round 1 - Foundations - Complete

**What was tested:** `lottie create`, `lottie run`, `lottie benchmark`, first agent (`DigestAgent`).

**Agent:** `DigestAgent` — takes a topic or block of text, returns a structured digest.

**Skill:** `SummarizerSkill` — stateless, typed I/O, wraps an LLM call to condense text.

**Results:** 6/6 test inputs passing · 100% coverage · injection attempt refused cleanly

Results logged in [`rounds/round-1-foundations/results.md`](rounds/round-1-foundations/results.md).

---

## Round 2 - Phase 0 Completion - Complete

**What was tested:** `lottie list`, `lottie inspect`, `lottie benchmark`, KI-01 empty query fix, second agent (`ReviewerAgent`).

**Benchmark (DigestAgent):**

| Provider | Cases | Accuracy | p50 | p95 | Cost/run |
|----------|-------|----------|-----|-----|----------|
| anthropic/claude-sonnet-4-6 | 3 | 100% | 7034ms | 7484ms | $0.0041 |

**Results:** 11/11 tests · 100% coverage · 2 agents in registry

Results logged in [`rounds/round-2-phase0-completion/results.md`](rounds/round-2-phase0-completion/results.md).

---

## How to run locally

```bash
# 1. Clone both repos side by side
git clone https://github.com/cdiaz19/lottie-lab.git
git clone https://github.com/cdiaz19/lottie-orchestrator.git
cd lottie-lab

# 2. Install Lottie
uv venv && source .venv/bin/activate

# Pre-PyPI: install from local clone
uv pip install -e ../lottie-orchestrator

# Once published to PyPI (coming with v0.1.0):
# uv pip install lottie-orchestrator

# 3. Add your API key
cp .env.example .env
# open .env and set ANTHROPIC_API_KEY or OPENAI_API_KEY

# 4. Check environment
lottie doctor

# 5. Run an agent
lottie run digest --input '{"query": "multi-agent AI systems"}'
lottie run reviewer --input '{"query": "Review this code: def add(a, b): return a + b"}'

# 6. Run tests (no API key needed)
pytest skills/ agents/ -v

# 7. Benchmark
lottie benchmark agent digest
```

> **Note:** `lottie-orchestrator` will be published to PyPI with the `v0.1.0` tag. Until then, clone it locally and install with `-e ../lottie-orchestrator`.

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
