# Round 4 — Results: Knowledge Core (Phase 1)

**Code under test:** `lottie-orchestrator` `main` @ `a0a3829` (merge of `feat/phase1-knowledge`, tag `v0.2.0`)
**Date:** 2026-06-10 · **venv:** `lottie-lab/.venv` (py 3.12.13, pytest 9.0.3) · **providers:** Mock (API keys UNSET)
**Raw data:** `outputs/` (A-schemas … ruff, input-*.out.json)

> Run from `lottie-orchestrator` (installed `-e` into the lab venv). networkx 3.6.1 + chromadb 1.5.9
> + numpy 2.4.6 were installed into the venv during preflight (the prior `-e` install predated the
> Phase-1 `networkx` core dependency — without it the CLI and all `lottie.knowledge` imports failed).

---

## 1. Sub-phase test groups

| Group | Command | Result |
|-------|---------|--------|
| A — schemas/frontmatter/manifest | `pytest .../test_schema.py .../test_frontmatter.py .../test_manifest.py` | ✅ **42 passed** |
| B — chunking | `pytest skills/chunker` | ✅ **16 passed** |
| C — embeddings | `pytest src/lottie/knowledge/embeddings` | ✅ **42 passed** |
| D — store + retrieval | `pytest src/lottie/knowledge/store skills/retrieval` | ✅ **102 passed** (incl. Chroma backend — chromadb installed, not skipped) |
| E — ingest + security | `pytest .../test_injection_scanner.py skills/document_ingest` | ✅ **36 passed** |
| F — graph + hybrid | `pytest .../test_graph.py skills/retrieval/tests/test_hybrid.py` | ✅ **41 passed** |
| G — research + summarizer | `pytest skills/summarizer agents/research` | ✅ **26 passed** |
| H — CLI | `pytest .../test_knowledge.py .../test_memory_cli.py .../test_run.py` | ✅ **42 passed** (after KI-R4-01 fix) |
| I — contracts | `pytest tests/contracts/test_knowledge_schema.py` | ✅ **43 passed** |
| I — benchmark | `lottie benchmark agent research` | ✅ **accuracy 100% · success 100%** (4 cases, MockLLM) |

---

## 2. Input cases (`run-inputs.sh` → `outputs/input-*.out.json`)

| Case | Surface | Status | Actual | Note |
|------|---------|--------|--------|------|
| input-01-ingest-text | `knowledge ingest --text` (draft, mock/embed, memory) | ✅ pass | `Ingested: 1 document(s), 1 chunk(s).` | clean source ingested |
| input-02-ingest-injection | `knowledge ingest --text` (injection payload) | ✅ pass | `Ingested: 0 document(s), 0 chunk(s).` + `Flagged (security gate): 1 source(s)`; **no `.md` written under `draft/`** | **CONSTRAINT met:** injection-flagged source gated, never stored |
| input-03-list | `knowledge list --root {FIXTURE}` | ✅ pass | table lists `global/conventions`, `lottie/auth`, `lottie/api` | 3 docs across global + platform |
| input-04-inspect | `knowledge inspect lottie/auth` | ✅ pass | id/layer/status/source + `depends_on=['global/conventions']`, `dependents=['lottie/api']`, `chunks=1` | metadata + resolved edges |
| input-05-memory-graph | `memory graph --root {FIXTURE}` | ✅ pass | `conventions → auth`, `auth → api`; `3 node(s), 2 edge(s).` | networkx graph from manifest |
| input-06-memory-impact | `memory impact global/conventions` | ✅ pass | `lottie/api`, `lottie/auth`; `2 document(s) transitively depend` | transitive descendants |
| input-07-memory-audit | `memory audit --root {FIXTURE}` | ✅ pass | `✓ no cycles` · `No orphans.` · `⚠ 1 stale document(s) … lottie/api` | acyclic; api stale (last_verified 2025-01) |
| input-08-run-research | `run research --input '{query…}'` | ✅ pass | typed `ResearchOutput` JSON: `digest` + `points` + `citations` (exit 0) | run from orchestrator cwd (no `--root` on `run`); grounded citations proven by benchmark + group G |

---

## 3. Full gate

| Gate | Command | Result |
|------|---------|--------|
| Full suite | `pytest -q` | ✅ **610 passed** in ~86s |
| Coverage | `pytest --cov=lottie --cov-report=term-missing` | ✅ **99%** (5073 stmts, 62 missed) — ≥ 80% |
| Types | `mypy --strict src` | ✅ **Success: no issues found in 128 source files** |
| Lint | `ruff check` | ✅ **All checks passed!** |

---

## 4. Constraints honored
- ✅ Ran with **API keys unset** — MockLLMProvider + MockEmbeddingProvider throughout.
- ✅ **Injection-flagged source never stored** (input-02: `draft/` empty after gate).
- ✅ Drafts written to `knowledge/draft/` only (ingest `--layer draft`).
- ✅ Agents reach the store only via the injected `RetrievalSkill` (no direct store access).
- ✅ Golden Rules: no vendor SDK in unit code; typed I/O everywhere (mypy --strict clean).

---

## 5. Known issues found in Round 4

- **KI-R4-01 — `test_knowledge.py` wrong typer import (FIXED).**
  `src/lottie/cli/tests/test_knowledge.py:14` imported `from typer._click.testing import Result`,
  which does not exist in the pinned typer (0.26.3) — collection error, group H could not run.
  `typer.testing` *does* export `Result` (and is what all 8 sibling CLI tests use). Fixed to
  `from typer.testing import CliRunner, Result`. Re-ran: 42 passed. Test-only change; no production
  code touched. Pre-existing in `feat/phase1-knowledge`; would have failed CI on this typer pin.

No open (unresolved) issues. No ❌.

---

## 6. Deviations from the runbook
- Verify commands run with **cwd = `lottie-orchestrator`** (code under test), per Round-3 precedent.
- Runbook selector `test_run.py::*research*` matches no node; ran full `test_run.py` instead
  (run-research path covered by `agents/research` group G + benchmark).

---

## 7. Overall — sign-off (20 boxes)

- [x] **1.** Knowledge schemas (pure Pydantic) — group A
- [x] **2.** YAML frontmatter parser — group A
- [x] **3.** `KnowledgeManifest` loader over `knowledge/` — group A
- [x] **4.** `ChunkerSkill` deterministic recursive splitter — group B
- [x] **5.** `EmbeddingProvider` ABC + `MockEmbeddingProvider` — group C
- [x] **6.** litellm embedding adapter (provider abstraction) — group C
- [x] **7.** `VectorStore` ABC + `InMemoryVectorStore` — group D
- [x] **8.** `ChromaVectorStore` backend — group D (chromadb installed, ran)
- [x] **9.** Typed `RetrievalSkill` (embed-query → scored hits) — group D
- [x] **10.** `PromptInjectionScanSkill` — group E
- [x] **11.** `DocumentIngestSkill` (load → scan → draft → chunk → embed → store) — group E + input-01/02
- [x] **12.** `GraphStore` over networkx (neighbors/impact/cycles/orphans/stale) — group F + input-05/06/07
- [x] **13.** Hybrid retrieval (vector + graph-neighbor expansion) — group F
- [x] **14.** `SummarizerSkill` (reference) — group G
- [x] **15.** `ResearchAgent` → typed `ResearchOutput` with citations — group G + input-08
- [x] **16.** CLI `lottie knowledge ingest|list|inspect|clear` — group H + input-01/03/04
- [x] **17.** CLI `lottie memory graph|impact|audit` — group H + input-05/06/07
- [x] **18.** `lottie run research` wiring (dependency-injection seam) — group H + input-08 + benchmark
- [x] **19.** Contract tests for all new schemas — group I
- [x] **20.** Full gate green: `pytest -q` (610), coverage 99% ≥ 80%, `mypy --strict`, `ruff`, `lottie benchmark agent research` 100%

**Boxes: 20 / 20.** Coverage **99%**. No ❌.
**Round 4: SIGNED OFF** → Phase 1 merges to `main`, tag **`v0.2.0`** (Knowledge Core), open **Round 5 — Phase 2 (Mesh)**.
