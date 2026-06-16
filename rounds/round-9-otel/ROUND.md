# Round 9 — Governance: OpenTelemetry Tracing

> Validate the SHIPPED OpenTelemetry tracing slice (governance slice 4, `lottie-orchestrator @
> feat/governance-otel`) from a downstream project — and **resolve the spec's open question**: do
> parallel LangGraph mesh worker spans nest under the mesh span across worker threads?

## Goal

Prove a span is emitted per run with the right scalar attributes; that tracing is a no-op when disabled
and fail-open when the tracer dies; that same-thread runs nest (agent→agent); and — the headline —
**determine whether parallel mesh worker spans nest under the mesh span** (the spec marked this
"expected but unverified", to be settled here).

## What's being tested

Every `BaseAgent` run hits `InstrumentedRunnable.run`, which emits an OTel span via
`governance.otel.run_span`. The driver installs an in-memory exporter (swapping opentelemetry's private
`_TRACER_PROVIDER`, since `set_tracer_provider` is once-per-process) and inspects span names +
parent-span links. Lab venv: orchestrator installed editable on `feat/governance-otel` + the `[otel]`
and `[mesh]` extras.

| # | Case | Checks |
|---|------|--------|
| 1 | Span per run | one span named after the agent, with `lottie.agent/kind/status/latency_ms/tokens/cost/provider` |
| 2 | Same-thread nesting | agent→agent on one thread; inner span parents to outer |
| 3 | **Parallel-mesh nesting** | a parallel LangGraph mesh with WORKER AGENTS; do their spans nest under the mesh span across threads? |
| 4 | No-op when disabled | `LOTTIE_DISABLE_OTEL=1` → zero spans |
| 5 | Fail-open | a tracer-setup failure must NOT break the run |

## Build / verify sequence

```bash
# orchestrator installed editable on feat/governance-otel; lab venv has [otel] + [mesh]
source .venv/bin/activate
uv pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http   # the [otel] deps
python3 rounds/round-9-otel/_otel_driver.py    # writes outputs/, prints PASS/FAIL + the nesting verdict
```

## Definition of done — ✅ COMPLETE (5/5)

Span per run with scalar attributes; same-thread nesting; no-op when disabled; fail-open on tracer
death; and the parallel-mesh nesting question **resolved**. **5/5 PASS** — and the parallel-mesh verdict
is **NESTS under the mesh span**: LangGraph copies the OTel context (contextvars-backed) into its worker
threads, so a parallel worker's span correctly parents to the mesh span — the same propagation property
the audit root-flag fix (`e99d42e`) relied on. The spec's "unverified" caveat is now **verified
positive**.

## Deviations / notes

- Validated **in-process** via the real `InstrumentedRunnable.run` hook with an in-memory span exporter
  — no live OTLP collector needed (the export path is the SDK's; the lab asserts the spans the framework
  produces). The parallel-mesh case (case 3) builds a minimal `MeshAgent` with worker **agents**
  (BaseAgents, which emit spans) fanned out via `LangGraphEngine` — EditorMesh's workers are pure
  functions and wouldn't emit worker spans.
- Scope is OpenTelemetry tracing. Per-`complete()` LLM child spans and denied-run spans are deferred
  framework slices, out of scope.
