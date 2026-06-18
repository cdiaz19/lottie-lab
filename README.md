# lottie-lab 🐶
> Public testing ground for [Lottie Orchestrator](https://github.com/cdiaz19/lottie-orchestrator) — a provider-agnostic multi-agent AI framework.

[![codecov](https://codecov.io/github/cdiaz19/lottie-lab/graph/badge.svg?token=TYML13AK0Z)](https://codecov.io/github/cdiaz19/lottie-lab)

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

Each round tackles a slice of the framework — usually the next phase, occasionally one pulled forward (MCP shipped early as Round 5). A round doesn't close until every item on its checklist is signed off.

| Round | Phase | Focus | Status |
|-------|-------|-------|--------|
| [Round 1](rounds/round-1-foundations/) | Phase 0 | Foundations — CLI, BaseAgent, BaseSkill, first agent end-to-end | Complete |
| [Round 2](rounds/round-2-phase0-completion/) | Phase 0 | Registry, benchmark, KI-01 fix, second agent | Complete |
| [Round 3](rounds/round-3-serve-core/) | Phase 0 | Serve core (`AgentService`), memory stubs, security write-gate — Phase 0 closed | Complete |
| [Round 4](rounds/round-4-knowledge/) | Phase 1 | Knowledge — document ingest, RAG pipeline, knowledge graph, `ResearchAgent` | Complete |
| [Round 5](rounds/round-5-mcp-transport/) | Phase 4 | MCP stdio transport — `lottie serve` (done early) | Complete |
| [Round 6](rounds/round-6-mesh/) | Phase 2 + 3 | Multi-agent mesh — LangGraph, supervisor→workers, parallel fan-out, HITL, time-travel | Complete |
| [Round 7](rounds/round-7-governance/) | Governance | Audit trail + capability policy engine (allow/deny/escalate) — 9/9, caught + fixed finding FG-1 | Complete |
| [Round 8](rounds/round-8-cost-budget/) | Governance | Cost budget circuit-breaker (per-agent, fail-closed) — 8/8 | Complete |
| [Round 9](rounds/round-9-otel/) | Governance | OpenTelemetry tracing — 5/5; parallel-mesh span nesting verified | Complete |
| [Round 10](rounds/round-10-openai-api/) | Phase 4 | OpenAI-compatible `/v1/chat/completions` transport (`lottie serve --port`) — 7/7; security + audit inherited | Complete |
| Round 11 | Phase 4 | remaining integration — generic REST (`/v1/agents/{name}/run`), streaming | Pending |

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

## Round 3 - Serve Core - Complete

**What was tested:** transport-agnostic serving core (`AgentService`), the serve-path security gate, the Phase 0 memory stubs, and the rule-13 security write-gate. Closes Phase 0.

**Serving core:** `AgentService.list_agents()` → `["digest", "reviewer"]` (import-free) · `run_agent("digest", payload)` → `RunResult` with latency, input/output tokens, and cost. Errors map to four typed exceptions: `AgentNotFoundError`, `InvalidInputError`, `AgentLoadError`, `AgentExecutionError`.

**Memory stubs:** `BaseAgent.memory` defaults to `NullMemoryClient` · `memory/schema.py` defines all 7 schemas · `MockMemoryClient` / `MockMemoryAgent` for store-free tests.

**Write-gate (rule-13):** `guard_and_write` runs SecretDetection → CodeSecurityScan → mypy → ruff; any failure removes the target dir — no partial/unsafe code survives.

**Results:** 224/224 tests · 99% coverage · serve 15, memory 18, security 17.

> **Caveat:** the serve-path `SecurityGate` chokepoint is wired (input before agent, output before return, order verified) and is constructor-injectable, but the **default gate is identity** — real input/output scanning lands in Phase 1. Injection blocking is demonstrated with a `BlockingGate` subclass, not active on the default path yet.

Results logged in [`rounds/round-3-serve-core/results.md`](rounds/round-3-serve-core/results.md).

---

## Round 4 - Knowledge Core - Complete

**What was tested:** Phase 1 knowledge layer end-to-end on Mock providers (API keys unset) — ingest → injection/secret scan → deterministic chunk → embed (provider abstraction) → vector store → typed `RetrievalSkill`; a networkx dependency graph answering `impact`/`audit`/cycle queries; and a reference `ResearchAgent` returning a typed `ResearchOutput` with citations.

**CLI:** `lottie knowledge ingest|list|inspect|clear` · `lottie memory graph|impact|audit` · `lottie run research`.

**Benchmark (ResearchAgent):**

| Provider | Cases | Accuracy | Success | p50 | p95 |
|----------|-------|----------|---------|-----|-----|
| anthropic/claude-sonnet-4-6 (MockLLM) | 4 | 100% | 100% | 5993ms | 8426ms |

**Results:** 610/610 tests · **99% coverage** · `mypy --strict` + `ruff` clean · 8/8 input cases · injection source gated & never stored. Found + fixed one Phase-1 test bug (KI-R4-01: wrong typer import). **20/20 sign-off boxes** → Phase 1 tagged `v0.2.0`.

> **How to run Round 4:** with API keys unset, from `lottie-orchestrator`:
> `pytest -q && pytest --cov=lottie && mypy --strict src && ruff check && lottie benchmark agent research`,
> then `bash rounds/round-4-knowledge/run-inputs.sh` from the lab. See [`rounds/round-4-knowledge/ROUND.md`](rounds/round-4-knowledge/ROUND.md).

Results logged in [`rounds/round-4-knowledge/results.md`](rounds/round-4-knowledge/results.md).

---

## Round 5 - MCP stdio Transport - Complete

**What was tested:** MCP stdio transport layer — `lottie serve` wiring, one typed tool per agent, `call_tool` routing, error mapping, optional-dep hygiene. Shipped early (Phase 4 slice 1), ahead of phase order.

Results logged in [`rounds/round-5-mcp-transport/results.md`](rounds/round-5-mcp-transport/results.md).

---

## Round 6 - Multi-agent Mesh - Complete

**What was tested:** supervisor→worker routing, parallel fan-out, HITL interrupt/resume, checkpoint time-travel, and capability enforcement — verified end-to-end from an independent lab mesh (`EditorMesh`) on the published API. Mock providers only; API keys unset.

**Mesh:** `EditorMesh` — topology `plan → parallel[draft, factcheck] → review → publish (HITL gate)`. Workers are pure deterministic stubs; the supervisor is the sole LLM consumer.

**Results:** 39 framework mesh tests (cwd=orchestrator, `[mesh]` extra) · 6 editor tests · 17 lab suite · 3/3 CLI cases (list, inspect, mesh-history) · in-process driver RESULT PASS (run status `interrupted`, history `['plan', 'draft', 'factcheck', 'review']`, resume status `complete`, final `PUBLISHED: ship the launch post`, 10 checkpoints) · `mypy --strict` clean (7 source files) · `ruff` clean.

> **How to run Round 6:** `uv pip install -e '../lottie-orchestrator[mesh]'`, then:
> `pytest agents/editor`, `bash rounds/round-6-mesh/run-inputs.sh`, `python3 rounds/round-6-mesh/_mesh_driver.py`.
> See [`rounds/round-6-mesh/results.md`](rounds/round-6-mesh/results.md) and [`rounds/round-6-mesh/ROUND.md`](rounds/round-6-mesh/ROUND.md).

> **Caveats:** The CLI's `build_provider` always returns `LiteLLMProvider`, so end-to-end routing/parallel/HITL/time-travel is proven by the in-process `_mesh_driver.py`, not via `lottie run`. The in-memory checkpointer is process-local — durable cross-process resume via sqlite is tracked as FU-9.

Results logged in [`rounds/round-6-mesh/results.md`](rounds/round-6-mesh/results.md).

---

## Round 8 - Cost Budget - Complete

**What was tested:** the per-agent cumulative **cost budget circuit-breaker** (governance slice 3) —
an agent declaring `budget_usd` is blocked once its prior recorded spend reaches the budget. Verified
end-to-end from the lab via the real `instantiate_agent` path + the real `DigestAgent`, with a
cost-reporting provider so spend actually accrues. A blocked run leaves the provider unconsumed
(`llm_calls=0`), proving it blocks before `_execute`.

**Results:** 8/8 cases — over-budget block (audited `budget_exceeded`); fail-closed when the audit
ledger is disabled (and scoped to a *configured* budget, so unbudgeted agents are unaffected); policy
checked before budget; the circuit breaker engaging on real accrual (`[ok, ok, BudgetExceeded]`, one-run
sequential overshoot); and `lottie audit` rendering the cost rows. No findings.

> **How to run Round 8:** orchestrator installed editable on `feat/governance-cost-budget`, then
> `python3 rounds/round-8-cost-budget/_cost_driver.py`. See
> [`rounds/round-8-cost-budget/results.md`](rounds/round-8-cost-budget/results.md) and
> [`rounds/round-8-cost-budget/ROUND.md`](rounds/round-8-cost-budget/ROUND.md).

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
