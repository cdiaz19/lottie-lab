# Round 9 — Governance: OpenTelemetry Tracing — Results

**Framework under test:** `lottie-orchestrator @ feat/governance-otel` (pushed; PR pending), installed
editable in the lab venv with the `[otel]` + `[mesh]` extras.
**Harness:** `_otel_driver.py` — every `BaseAgent` run hits `InstrumentedRunnable.run` → `run_span`. An
`InMemorySpanExporter` is installed by swapping opentelemetry's private `_TRACER_PROVIDER`
(`set_tracer_provider` is once-per-process); spans inspected by name + parent link.

**Headline: 5/5 pass. The spec's open question is RESOLVED POSITIVE — parallel LangGraph mesh worker
spans NEST under the mesh span across worker threads.**

## Test matrix

| # | Case | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Span per run | one span + `lottie.*` attrs | span `digest` with `lottie.agent/kind/status=ok/latency_ms/input_tokens/output_tokens/cost_usd/provider` | ✅ |
| 2 | Same-thread nesting | inner parents to outer | `inner.parent.span_id == outer.span_id` | ✅ |
| 3 | **Parallel-mesh nesting** | resolve nest-vs-root | spans `[worker-a, worker-b, mesh]`; **both worker parents = mesh** → NESTS | ✅ |
| 4 | No-op when disabled | zero spans | `LOTTIE_DISABLE_OTEL=1` → 0 spans after a run | ✅ |
| 5 | Fail-open | run unaffected | `_ensure_provider` forced to raise → run returns `resilient:done` normally | ✅ |

## The headline finding — parallel-mesh nesting VERIFIED

The OTel spec (slice 4) marked cross-thread parallel-mesh span nesting **"expected but unverified"** —
OTel context is contextvars-backed (like the audit depth), but OTel context does not auto-propagate into
arbitrary threads without `copy_context`, so whether LangGraph's fork carries the active span was an open
question deferred to this round.

**Verdict: it nests.** A parallel mesh with two worker agents (`worker-a`, `worker-b`) fanned out via
`LangGraphEngine`, run with tracing on, produced spans whose **parents are both the `mesh` span**, not
root. LangGraph copies the OTel context into its worker threads — the **same propagation property the
audit root-flag fix (`e99d42e`) relied on** — so a parallel worker's span correctly parents to the
supervisor's span. The framework's original spec claim was correct; the conservative "unverified"
softening can be upgraded to **verified**.

> Follow-up (framework record): the OTel design doc on `feat/governance-otel` still reads
> "unverified — validated in Round 9". It should be updated to "verified: nests (Round 9)" so the spec
> matches reality before merge (the FG-1 "don't leave a stale artifact" discipline).

## Proof points

- **Per-run span + scalar attributes** (case 1): one span per `BaseAgent.run`, attributes name/kind/
  status/latency/tokens/cost/provider — **no raw payloads** (privacy parity with audit). `cost_usd=0.0`
  because the mock provider reports no cost.
- **Same-thread nesting** (case 2): an agent whose `_execute` runs another agent → the inner run's span
  parents to the outer — OTel's current-context nesting on one thread.
- **Cross-thread nesting** (case 3): the headline — parallel worker spans parent to the mesh span.
- **No-op when off** (case 4): `LOTTIE_DISABLE_OTEL=1` → `run_span` yields nothing, zero spans, run still
  completes — the default-off / base-install posture.
- **Fail-open** (case 5): forcing the tracer provider setup to raise leaves the run completely unaffected
  (returns its output) — observability never breaks execution.

## Findings

No defects. One spec-accuracy follow-up (above): upgrade the OTel design doc's parallel-nesting note from
"unverified" to "verified" now that Round 9 settled it positively.

## §7 Sign-off checklist

- [x] One OTel span per agent run with `lottie.*` scalar attributes (no raw payloads)
- [x] Same-thread nesting (agent→agent): inner parents to outer
- [x] **Parallel-mesh nesting resolved: worker spans NEST under the mesh span** (cross-thread)
- [x] No-op when `LOTTIE_DISABLE_OTEL=1` (zero spans, run completes)
- [x] Fail-open: a tracer-setup failure does not break the run
- [x] Findings recorded honestly (spec-accuracy follow-up noted)

**Verdict:** OpenTelemetry tracing validated end-to-end — **5/5** — and the parallel-mesh nesting open
question is settled **positive** (nests). No orchestrator PR merged by this round; `feat/governance-otel`
awaits review (and the one-line spec accuracy update).
