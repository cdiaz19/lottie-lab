"""Round-17 cost-caps driver — validate orchestrator S3 (per-run token cap + TOCTOU-safe
atomic cost reservation) from a downstream project.

Runs the real shipped path in-process via `instantiate_agent` (attaches the cost gate from
config.budget_usd / config.max_run_usd and the token cap from config.max_run_tokens). Uses a
per-test temp project root with audit ENABLED so the reservation ledger is live, and a
usage-reporting provider so the token cap has real tokens to count.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

# Reservation + token-cap live in the audit ledger -> audit must be ON for this round.
os.environ.pop("LOTTIE_DISABLE_AUDIT", None)

from lottie.governance.cost import BudgetExceeded, TokenCapExceeded  # noqa: E402
from lottie.llm import LLMResponse, Message  # noqa: E402
from lottie.llm.base import LLMProvider, TokenUsage  # noqa: E402
from lottie.project.config import AgentConfig  # noqa: E402
from lottie.project.discovery import instantiate_agent  # noqa: E402

from agents.digest.agent import DigestAgent  # noqa: E402
from agents.digest.schema import DigestAgentInput  # noqa: E402

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent


class _UsageProvider(LLMProvider):
    def __init__(self, in_tok: int, out_tok: int) -> None:
        self._in, self._out = in_tok, out_tok

    @property
    def model(self) -> str:
        return "usage/sim"

    def complete(
        self, messages: list[Message], model_params: Mapping[str, object] | None = None
    ) -> LLMResponse:
        return LLMResponse(
            content="a digest",
            usage=TokenUsage(input_tokens=self._in, output_tokens=self._out),
            model="usage/sim",
            cost_usd=0.0,
        )


class _PricedProvider(_UsageProvider):
    """A provider that reports a real cost, so committed spend accrues in the ledger.

    `_UsageProvider` reports cost_usd=0.0, which is exactly why this round passed
    unchanged through the regression that left the audit ledger recording free runs:
    with no cost to lose, there was nothing to notice.
    """

    def __init__(self, in_tok: int, out_tok: int, cost: float) -> None:
        super().__init__(in_tok, out_tok)
        self._cost = cost

    def complete(
        self, messages: list[Message], model_params: Mapping[str, object] | None = None
    ) -> LLMResponse:
        base = super().complete(messages, model_params)
        return LLMResponse(
            content=base.content, usage=base.usage, model=base.model, cost_usd=self._cost
        )


def _config(**kw: object) -> AgentConfig:
    return AgentConfig.model_validate({"provider": "usage/sim", **kw})


def _digest(root: Path, provider: LLMProvider, **cfg: object) -> DigestAgent:
    return instantiate_agent(  # type: ignore[return-value]
        DigestAgent, llm=provider, root=root, config=_config(**cfg), enable_benchmarks=False
    )


def _emit(name: str, detail: str, ok: bool) -> bool:
    (OUTPUTS / f"case-{name}.out.txt").write_text(
        f"{'PASS' if ok else 'FAIL'} — {name}\n\n{detail}\n", encoding="utf-8"
    )
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def case_01_atomic_admission_blocks_concurrent() -> bool:
    """A concurrent in-flight reservation is counted -> the second run is refused (TOCTOU)."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        a1 = _digest(root, _UsageProvider(1, 1), budget_usd=10.0, max_run_usd=6.0)
        a2 = _digest(root, _UsageProvider(1, 1), budget_usd=10.0, max_run_usd=6.0)
        held = a1._cost.reserve()  # simulate a1's run in flight (reserved 6, not settled)
        blocked = False
        try:
            a2.run(DigestAgentInput(query="x"))  # 6 + 6 > 10 -> refused
        except BudgetExceeded:
            blocked = True
        return _emit(
            "01-atomic-admission",
            "budget=10, max_run_usd=6; one reservation held (6) -> a concurrent run's "
            f"reservation (6) is refused: committed+reserved+amount > budget. blocked={blocked} "
            f"held_handle={held is not None}",
            blocked and held is not None,
        )


def case_02_settle_frees_headroom() -> bool:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        a = _digest(root, _UsageProvider(1, 1), budget_usd=10.0, max_run_usd=6.0)
        a.run(DigestAgentInput(query="x"))  # reserves then settles
        # a second sequential run is admitted again (headroom freed on settle)
        out = a.run(DigestAgentInput(query="y"))
        return _emit(
            "02-settle-frees",
            f"sequential gated runs both admitted (reservation settled between). result={out.result!r}",
            out.result == "a digest",
        )


def case_03_token_cap_aborts_runaway() -> bool:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # digest calls complete() once with 10 tokens; cap of 5 -> abort
        a = _digest(root, _UsageProvider(6, 6), max_run_tokens=5)
        capped = False
        try:
            a.run(DigestAgentInput(query="x"))
        except TokenCapExceeded:
            capped = True
        return _emit(
            "03-token-cap",
            f"max_run_tokens=5, run accrues 12 -> TokenCapExceeded mid-run. capped={capped}",
            capped,
        )


def case_04_legacy_budget_still_blocks() -> bool:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # legacy: budget set, max_run_usd None. Seed spend to the budget via a real run first.
        a = _digest(root, _UsageProvider(1, 1), budget_usd=0.0)  # budget 0 -> any prior spend blocks
        # a fresh ledger has spent 0; 0 >= 0 -> blocked on the first run (cumulative check)
        blocked = False
        try:
            a.run(DigestAgentInput(query="x"))
        except BudgetExceeded:
            blocked = True
        # Positive control: budget 0 blocks for ANY ledger state, including a broken one
        # that always reads zero. Assert the same config with headroom ADMITS the run, so
        # the block above is attributable to the budget and not to a permanently-on gate.
        b = _digest(root, _UsageProvider(1, 1), budget_usd=1.0)
        admitted = False
        try:
            b.run(DigestAgentInput(query="y"))
            admitted = True
        except BudgetExceeded:
            pass
        return _emit(
            "04-legacy-cumulative",
            f"budget_usd=0, max_run_usd=None -> legacy cumulative check blocks (spent 0 >= 0). "
            f"blocked={blocked}\nControl: budget_usd=1.0 with an empty ledger ADMITS, so the "
            f"block is the budget and not an always-on gate. admitted={admitted}",
            blocked and admitted,
        )


def case_05_fail_closed_disabled_ledger() -> bool:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        os.environ["LOTTIE_DISABLE_AUDIT"] = "1"
        try:
            a = _digest(root, _UsageProvider(1, 1), budget_usd=10.0, max_run_usd=6.0)
            blocked = False
            try:
                a.run(DigestAgentInput(query="x"))
            except BudgetExceeded:
                blocked = True
        finally:
            os.environ.pop("LOTTIE_DISABLE_AUDIT", None)
        return _emit(
            "05-fail-closed",
            f"budget set + audit ledger disabled -> reserve() fails closed (never admits). blocked={blocked}",
            blocked,
        )


def case_06_committed_spend_constrains_the_next_reservation() -> bool:
    """The case that was DEAD: real spend from a finished run must shrink the headroom.

    budget $10, max_run_usd $6, $5 per run. Run 1 is admitted ($0 committed + $6 hold).
    It settles, leaving $5 committed. Run 2 needs $5 + $6 = $11 > $10, so it is refused.

    While the audit ledger recorded every run as free, committed stayed $0 forever and run
    2 was admitted — `max_run_usd` and `budget_usd` together bounded nothing but
    concurrency. Every other case in this round still passed, because none of them spent
    anything.
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        a = _digest(root, _PricedProvider(1, 1, 5.0), budget_usd=10.0, max_run_usd=6.0)
        a.run(DigestAgentInput(query="x"))  # admitted; settles, committing $5
        from lottie.governance.audit import SqliteAuditLogger

        committed = SqliteAuditLogger(root).total_cost("DigestAgent")
        blocked = False
        try:
            a.run(DigestAgentInput(query="y"))
        except BudgetExceeded:
            blocked = True
        return _emit(
            "06-committed-spend",
            f"budget=10, max_run_usd=6, $5/run. Run 1 admitted and settled -> committed="
            f"${committed:.2f}. Run 2 needs committed+amount=11 > 10 -> refused. "
            f"blocked={blocked}",
            blocked and abs(committed - 5.0) < 1e-9,
        )


def main() -> int:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    cases = [
        case_01_atomic_admission_blocks_concurrent,
        case_02_settle_frees_headroom,
        case_03_token_cap_aborts_runaway,
        case_04_legacy_budget_still_blocks,
        case_05_fail_closed_disabled_ledger,
        case_06_committed_spend_constrains_the_next_reservation,
    ]
    results = [c() for c in cases]
    passed, total = sum(results), len(results)
    print(f"\nRESULT: {passed}/{total} cases PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
