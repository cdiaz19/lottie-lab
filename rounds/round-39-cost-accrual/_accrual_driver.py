"""Round-39 cost-accrual driver — a governance control that had gone silently dead.

Found by re-running round 8 during a routine regression sweep, not by any unit test.
Case 07 of that round ("the cumulative budget breaker engages on real accrual") had been
recorded PASS in the v1 era and now failed: three $0.04 runs against a $0.05 budget all
succeeded, and the ledger reported a final spend of $0.0000.

Root cause: two accumulators.

  * `Pipeline` builds the run's usage accumulator up front (via `usage_factory`) and
    reads it back when it emits `RunCompleted`.
  * `InstrumentedRunnable.run` then started a SECOND `RunContext` and published THAT one
    as `_active_ctx`, which is what every `complete()` call accrues into.

So the object the pipeline reported from was never written to. Since V3 S4 moved auditing
out of the middleware chain and onto the bus, the audit row is built from that event —
and every row recorded a free run. `budget_usd` sums that ledger, so the cumulative cost
circuit-breaker could never fire. Per-run caps (`max_run_usd`, `max_run_tokens`) read
`_active_ctx` directly and were unaffected, which is exactly why this stayed hidden.

The fix makes `run` ADOPT a context the caller already published instead of replacing it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from contextlib import chdir
from pathlib import Path

from lottie.governance.audit import SqliteAuditLogger
from lottie.governance.cost import BudgetExceeded, build_cost_gate
from lottie.llm import LLMResponse, Message
from lottie.llm.base import LLMProvider, TokenUsage
from lottie.project.config import AgentConfig
from lottie.project.discovery import instantiate_agent
from lottie.runtime.events import RunCompleted, RunEvent

from agents.digest.agent import DigestAgent
from agents.digest.schema import DigestAgentInput

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
OUTPUTS.mkdir(parents=True, exist_ok=True)
_AGENT = "DigestAgent"

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


class _CostProvider(LLMProvider):
    """Reports a fixed cost and token count per call, so a run accrues real spend."""

    def __init__(self, cost: float) -> None:
        self._cost = cost
        self.calls = 0

    @property
    def model(self) -> str:
        return "cost/sim"

    def complete(
        self, messages: list[Message], model_params: Mapping[str, object] | None = None
    ) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            content="DIGEST: a concise summary.",
            usage=TokenUsage(input_tokens=10, output_tokens=20),
            model="cost/sim",
            cost_usd=self._cost,
        )


class _Collector:
    name = "collector"

    def __init__(self) -> None:
        self.seen: list[RunEvent] = []

    def on_event(self, event: RunEvent) -> None:
        self.seen.append(event)


def _agent(root: Path, provider: _CostProvider, budget: float | None = None) -> DigestAgent:
    agent = instantiate_agent(  # type: ignore[return-value]
        DigestAgent,
        llm=provider,
        root=root,
        config=AgentConfig.model_validate(
            {"provider": "cost/sim", "budget_usd": budget, "capabilities": ["text.summarize"]}
        ),
        enable_benchmarks=False,
    )
    if budget is not None:
        agent.set_cost_gate(build_cost_gate(root, agent=_AGENT, budget_usd=budget))
    return agent


_SCRATCH = Path(tempfile.mkdtemp(prefix="round39-"))
try:
    # --- Case 1: the ledger records what the run actually spent ---------------
    root = _SCRATCH / "one"
    root.mkdir()
    with chdir(root):
        _agent(root, _CostProvider(0.04)).run(DigestAgentInput(query="summarize"))
    row = SqliteAuditLogger(root).query(limit=5)[0]
    check(
        "1. the audit row carries the run's real cost, not zero",
        abs(row.cost_usd - 0.04) < 1e-9,
        f"cost_usd={row.cost_usd}",
    )

    # --- Case 2: tokens travel the same path and were equally lost ------------
    check(
        "2. the audit row carries the run's real token counts",
        (row.input_tokens, row.output_tokens) == (10, 20),
        f"tokens={row.input_tokens}/{row.output_tokens}",
    )

    # --- Case 3: the two accumulators must agree ------------------------------
    # The bug was that they diverged, and only one of them was ever asserted.
    root = _SCRATCH / "agree"
    root.mkdir()
    with chdir(root):
        agent = _agent(root, _CostProvider(0.04))
        agent.run(DigestAgentInput(query="summarize"))
        metrics = agent.last_metrics
    ledger_cost = SqliteAuditLogger(root).query(limit=5)[0].cost_usd
    check(
        "3. the ledger agrees with the agent's own metrics",
        metrics is not None and abs(ledger_cost - metrics.cost_usd) < 1e-9,
        f"ledger={ledger_cost} metrics={metrics.cost_usd if metrics else None}",
    )

    # --- Case 4: spend accumulates across runs --------------------------------
    root = _SCRATCH / "accrue"
    root.mkdir()
    with chdir(root):
        agent = _agent(root, _CostProvider(0.04))
        for _ in range(3):
            agent.run(DigestAgentInput(query="summarize"))
    total = SqliteAuditLogger(root).total_cost(_AGENT)
    check(
        "4. total_cost accumulates across runs",
        abs(total - 0.12) < 1e-9,
        f"total=${total:.4f}",
    )

    # --- Case 5: the cumulative circuit-breaker fires -------------------------
    # THE headline. budget $0.05, $0.04/run: run 2 crosses, run 3 is refused.
    root = _SCRATCH / "breaker"
    root.mkdir()
    provider = _CostProvider(0.04)
    outcomes: list[str] = []
    with chdir(root):
        agent = _agent(root, provider, budget=0.05)
        for _ in range(3):
            try:
                agent.run(DigestAgentInput(query="summarize"))
                outcomes.append("ok")
            except BudgetExceeded:
                outcomes.append("BudgetExceeded")
    check(
        "5. the cumulative budget breaker refuses the run after the budget is crossed",
        outcomes == ["ok", "ok", "BudgetExceeded"],
        f"outcomes={outcomes}",
    )

    # --- Case 6: a blocked run never reaches the provider ---------------------
    check(
        "6. the blocked run never spent a token — the gate is fail-closed",
        provider.calls == 2,
        f"provider_calls={provider.calls} (expect 2, the two admitted runs)",
    )

    # --- Case 7: `lottie audit` shows an operator the real numbers ------------
    # The CLI is how a human sees spend. It had been rendering 0/0 and $0.000000
    # for every run since S4, which reads as "this agent is free".
    root = _SCRATCH / "cli"
    root.mkdir()
    (root / "lottie.yaml").write_text(
        "project: accrual-demo\nproviders:\n  default: cost/sim\n", encoding="utf-8"
    )
    with chdir(root):
        _agent(root, _CostProvider(0.01)).run(DigestAgentInput(query="summarize"))
        cli = subprocess.run(
            [str(Path(sys.executable).parent / "lottie"), "audit"],
            capture_output=True,
            text=True,
            cwd=root,
        )
    rendered = cli.stdout + cli.stderr
    (OUTPUTS / "case-07-audit-cli.out.txt").write_text(rendered, encoding="utf-8")
    check(
        "7. `lottie audit` renders the real cost to an operator",
        cli.returncode == 0 and "10/20" in rendered and "0.010000" in rendered,
        f"exit={cli.returncode}",
    )

    # --- Case 8: a telemetry plugin sees the real cost too --------------------
    # E7 made the bus a public extension point. The same zeroed event reached every
    # third-party subscriber, so a cost exporter reported a free fleet.
    root = _SCRATCH / "plugin"
    root.mkdir()
    collector = _Collector()
    with chdir(root):
        agent = _agent(root, _CostProvider(0.04))
        agent.set_plugins([collector])  # type: ignore[arg-type]
        agent.run(DigestAgentInput(query="summarize"))
    completed = [e for e in collector.seen if isinstance(e, RunCompleted)]
    check(
        "8. a plugin subscriber sees the real cost on RunCompleted",
        len(completed) == 1 and abs(completed[0].cost_usd - 0.04) < 1e-9,
        f"events={len(completed)} cost={completed[0].cost_usd if completed else None}",
    )

    # --- Case 9: the accumulator does not outlive its run --------------------
    # It is published BEFORE the chain runs, so a gate aborting ahead of `_execute`
    # would otherwise leave it dangling into the next call on the same agent.
    root = _SCRATCH / "leak"
    root.mkdir()
    with chdir(root):
        agent = _agent(root, _CostProvider(0.04), budget=0.01)
        agent.run(DigestAgentInput(query="summarize"))  # post-hoc accrual: this crosses
        blocked = False
        try:
            agent.run(DigestAgentInput(query="summarize"))
        except BudgetExceeded:
            blocked = True
    check(
        "9. the usage accumulator is cleared even when a gate aborts the run",
        blocked and agent._active_ctx is None,
        f"blocked={blocked} active_ctx={agent._active_ctx!r}",
    )

    # --- Case 10: a free provider still records zero -------------------------
    # The fix must not invent spend where there is none.
    root = _SCRATCH / "free"
    root.mkdir()
    with chdir(root):
        _agent(root, _CostProvider(0.0)).run(DigestAgentInput(query="summarize"))
    free_row = SqliteAuditLogger(root).query(limit=5)[0]
    check(
        "10. a genuinely free run still records $0.00",
        free_row.cost_usd == 0.0 and free_row.input_tokens == 10,
        f"cost={free_row.cost_usd} tokens={free_row.input_tokens}/{free_row.output_tokens}",
    )

finally:
    import shutil

    shutil.rmtree(_SCRATCH, ignore_errors=True)

passed = sum(1 for _, ok, _ in results if ok)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        [{"case": n, "pass": ok, "detail": d} for n, ok, d in results], indent=2
    ),
    encoding="utf-8",
)
print(f"\nRESULT {'PASS' if passed == len(results) else 'FAIL'} — {passed}/{len(results)}")
sys.exit(0 if passed == len(results) else 1)
