# Round 4 — Knowledge Core (Phase 1)
> Ingest → scan → chunk → embed → store → retrieve · networkx dependency graph · reference `ResearchAgent` · `lottie knowledge`/`memory`/`run research` CLI

## Goal
Verify **Phase 1 — Knowledge Layer** of `lottie-orchestrator` end-to-end on **Mock providers
(API keys unset)** and sign off the Round-4 checklist (§7) so Phase 1 can merge to `main` and tag
`v0.2.0` ("Knowledge Core"). Phase 1 is done when a document can be ingested into the `knowledge/`
layer (injection + secret scanned first), chunked deterministically, embedded through the provider
abstraction, stored in a vector backend, and retrieved by a typed `RetrievalSkill`; when the
networkx dependency graph builds from the manifest and answers `impact`/`audit`/cycle queries; when
a reference `ResearchAgent` runs end-to-end on `MockLLMProvider` + a fixture index and returns a
typed `ResearchOutput` with citations; when `lottie knowledge ingest|list|inspect|clear`,
`lottie memory graph|impact|audit`, and `lottie run research` work; and when unit + integration +
contract tests are green with coverage ≥ 80% and `lottie benchmark agent research` runs.

## What's being tested
1. **Schemas + frontmatter + manifest** (sub-phase A) — pure Pydantic shapes, YAML frontmatter parser, `KnowledgeManifest` loader.
2. **Chunking** (B) — deterministic recursive char splitter (`ChunkerSkill`).
3. **Embeddings** (C) — `EmbeddingProvider` ABC + `MockEmbeddingProvider` + litellm adapter.
4. **Vector store + retrieval** (D) — `VectorStore` ABC, `InMemoryVectorStore`, `ChromaVectorStore`, typed `RetrievalSkill`.
5. **Ingest + security** (E) — `PromptInjectionScanSkill` + `DocumentIngestSkill` (load → scan → draft → chunk → embed → store). Injection/secret sources are gated, never stored.
6. **Knowledge graph** (F) — `GraphStore` over networkx (`neighbors`/`impact`/`cycles`/`orphans`/`stale`) + hybrid retrieval (vector + graph expansion).
7. **ResearchAgent + Summarizer** (G) — typed `ResearchOutput` digest with citations on Mock providers.
8. **CLI surface** (H) — `lottie knowledge`, `lottie memory`, `lottie run research`.
9. **Contracts + benchmark** (I) — schema contract tests + `lottie benchmark agent research` eval suite.
10. **Full gate** — `pytest -q`, coverage ≥ 80%, `mypy --strict`, `ruff`.

## Build / verify sequence

```bash
# From lottie-orchestrator (installed -e into the lab venv), API keys UNSET.
# Outputs are tee'd into ../lottie-lab/rounds/round-4-knowledge/outputs/.
pytest src/lottie/knowledge/tests/test_schema.py src/lottie/knowledge/tests/test_frontmatter.py src/lottie/knowledge/tests/test_manifest.py -v   # A-schemas
pytest skills/chunker -v                                                                  # B-chunking
pytest src/lottie/knowledge/embeddings -v                                                 # C-embeddings
pytest src/lottie/knowledge/store skills/retrieval -v                                      # D-store-retrieval
pytest src/lottie/security/tests/test_injection_scanner.py skills/document_ingest -v       # E-ingest-security
pytest src/lottie/knowledge/tests/test_graph.py skills/retrieval/tests/test_hybrid.py -v   # F-graph
pytest skills/summarizer agents/research -v                                                # G-research
pytest src/lottie/cli/tests/test_knowledge.py src/lottie/cli/tests/test_memory_cli.py src/lottie/cli/tests/test_run.py -v   # H-cli
pytest tests/contracts/test_knowledge_schema.py -v                                         # I-contracts
lottie benchmark agent research                                                            # I-benchmark
pytest -q                                                                                  # full-suite
pytest --cov=lottie --cov-report=term-missing                                              # coverage
mypy --strict src                                                                          # mypy
ruff check                                                                                 # ruff
```

Then run the input cases:

```bash
bash rounds/round-4-knowledge/run-inputs.sh   # 8 cases → outputs/input-*.out.json
```

## Inputs
See `inputs/`. Each `input-*.json` carries `_case`, `argv`, and `_expect_*` checks driven by
`run-inputs.sh`. `inputs/fixture/knowledge/` is a small 3-doc graph
(`global/conventions → lottie/auth → lottie/api`) used by the list/inspect/memory cases.
Raw results land in `outputs/`; the signed-off summary is `results.md`.

## Definition of done
Every box in `results.md` §7 checked, full suite green, coverage ≥ 80%, `mypy --strict` + `ruff`
clean, injection/secret sources gated (never stored), `ResearchAgent` returns a typed
`ResearchOutput`. Round 4 done → merge Phase 1 to `main`, tag `v0.2.0`, open Round 5 (Phase 2 — Mesh).

## Deviations from plan
- **Test path scope.** The verify commands run with **cwd = `lottie-orchestrator`** (the code under
  test, installed `-e`), as established in Round 3. The lab folder only holds the harness
  (`ROUND.md`/`inputs`/`outputs`/`results.md`).
- **`test_run.py::*research*` selector** (in the original runbook) matches no node — `test_run.py`
  has no research-specific test. Ran the full `test_run.py` instead; the `run research` path is
  covered by `agents/research` (group G) + `lottie benchmark agent research`.
- **KI-R4-01 (fixed).** `src/lottie/cli/tests/test_knowledge.py` imported the nonexistent
  `typer._click.testing.Result` (typer 0.26.3). Corrected to `from typer.testing import CliRunner,
  Result` — the public API used by all sibling CLI tests. See `results.md` → Known issues.
