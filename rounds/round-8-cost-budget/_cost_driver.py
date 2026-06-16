"""Round-8 cost-budget driver — validate the per-agent cumulative cost circuit-breaker
against lottie-orchestrator @ feat/governance-cost-budget.

Runs the REAL shipped path in-process: `instantiate_agent` (which attaches the cost gate
from config.budget_usd) + the real `DigestAgent`. Two provider styles:
  * a cost-reporting `_CostProvider` (LLMResponse.cost_usd > 0) so a real run ACCRUES
    spend into the audit ledger — used to demonstrate the circuit breaker dynamically;
  * pre-seeded audit rows for deterministic over-budget / fail-closed cases.

A blocked run leaves the provider unconsumed (calls == 0), proving `_execute` never ran.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from contextlib import chdir
from pathlib import Path

from lottie.governance.audit import SqliteAuditLogger
from lottie.governance.cost import BudgetExceeded
from lottie.governance.policy import PolicyDenied
from lottie.governance.schema import AuditRecord
from lottie.llm import LLMResponse, Message
from lottie.llm.base import LLMProvider, TokenUsage
from lottie.project.config import AgentConfig
from lottie.project.discovery import instantiate_agent

from agents.digest.agent import DigestAgent
from agents.digest.schema import DigestAgentInput

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
_AGENT = "DigestAgent"  # DigestAgent's metrics name (class-derived) = the ledger key


class _CostProvider(LLMProvider):
    """Provider that reports a fixed cost_usd per call (so runs accrue real spend)."""

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


def _config(budget: float | None, *, capabilities: list[str], policies: list[str]) -> AgentConfig:
    return AgentConfig.model_validate(
        {
            "provider": "cost/sim",
            "budget_usd": budget,
            "capabilities": capabilities,
            "policies": policies,
        }
    )


def _seed(root: Path, cost: float) -> None:
    SqliteAuditLogger(root).log(
        AuditRecord(
            ts="2026-06-14T10:00:00+00:00", agent=_AGENT, provider="cost/sim", status="ok",
            root=True, input_sha256="a" * 64, output_sha256="b" * 64, input_tokens=0,
            output_tokens=0, cost_usd=cost, latency_ms=1.0, error=None,
        )
    )


def _write_base_policy(root: Path, deny: list[str]) -> None:
    pol = root / "policies"
    pol.mkdir(parents=True, exist_ok=True)
    body = "name: base\n" + (f"deny: [{', '.join(deny)}]\n" if deny else "")
    (pol / "base.yaml").write_text(body, encoding="utf-8")


def _run_once(
    root: Path, cfg: AgentConfig, provider: _CostProvider
) -> tuple[str, int, str]:
    """Instantiate + run digest once. Return (outcome, provider_calls, detail)."""
    try:
        agent = instantiate_agent(DigestAgent, llm=provider, root=root, config=cfg)
        out = agent.run(DigestAgentInput(query="Summarize multi-agent AI systems."))
    except BudgetExceeded as exc:
        return ("BudgetExceeded", provider.calls, f"BudgetExceeded: {exc}")
    except PolicyDenied as exc:
        return ("PolicyDenied", provider.calls, f"PolicyDenied: {exc}")
    except Exception as exc:  # noqa: BLE001
        return (type(exc).__name__, provider.calls, f"{type(exc).__name__}: {exc}")
    return ("ok", provider.calls, f"ok: {out.result[:48]}")


def _audit_status(root: Path) -> str:
    try:
        rows = SqliteAuditLogger(root).query(limit=1)
    except Exception:  # noqa: BLE001
        return "(no audit db)"
    return rows[0].status if rows else "(empty)"


# (id, desc, budget, seed_cost, deny, disable_audit, expect, expect_status)
CASES = [
    ("01-no-budget", "No budget declared -> unlimited (baseline).",
     None, None, [], False, "ok", "ok"),
    ("02-under-budget", "Budget set, prior spend below it -> run proceeds.",
     0.10, 0.02, [], False, "ok", "ok"),
    ("03-over-budget", "Prior spend >= budget -> BudgetExceeded, blocked before _execute.",
     0.05, 0.05, [], False, "BudgetExceeded", "budget_exceeded"),
    ("04-fail-closed-audit-off", "Budget set + audit disabled -> fail-closed BudgetExceeded.",
     0.05, None, [], True, "BudgetExceeded", None),
    ("05-no-budget-audit-off", "No budget + audit disabled -> runs (fail-closed scopes to a budget).",
     None, None, [], True, "ok", None),
    ("06-policy-before-budget", "Policy-denied AND over budget -> PolicyDenied (policy first).",
     0.05, 0.05, ["text.summarize"], False, "PolicyDenied", "denied"),
]


def _run_case(case: tuple) -> bool:
    cid, desc, budget, seed, deny, disable_audit, expect, want_status = case
    if disable_audit:
        os.environ["LOTTIE_DISABLE_AUDIT"] = "1"
    else:
        os.environ.pop("LOTTIE_DISABLE_AUDIT", None)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        if deny:
            _write_base_policy(root, deny)
        caps = ["text.summarize"]
        policies = ["base"] if deny else []
        if seed is not None:
            _seed(root, seed)
        provider = _CostProvider(0.0)
        with chdir(root):
            outcome, calls, detail = _run_once(
                root, _config(budget, capabilities=caps, policies=policies), provider
            )
            status = _audit_status(root) if not disable_audit else "(audit off)"
    ok = outcome == expect
    if outcome in {"BudgetExceeded", "PolicyDenied"} and calls != 0:
        ok = False  # a block must not have invoked the LLM
    if want_status is not None and not disable_audit and status != want_status:
        ok = False
    body = (
        f"CASE {cid}: {desc}\nbudget={budget} seed={seed} deny={deny} audit_off={disable_audit}\n"
        f"outcome={outcome} (expect {expect}) llm_calls={calls} audit_status={status}\n{detail}\n"
        f"RESULT: {'PASS' if ok else 'FAIL'}\n"
    )
    (OUTPUTS / f"case-{cid}.out.txt").write_text(body, encoding="utf-8")
    print(f"[{'PASS' if ok else 'FAIL'}] case {cid}: outcome={outcome} calls={calls} status={status}")
    return ok


def _run_accrual() -> bool:
    """Case 07: real accrual. budget 0.05, 0.04/run. run1 ok, run2 ok (crosses), run3 blocked."""
    os.environ.pop("LOTTIE_DISABLE_AUDIT", None)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cfg = _config(0.05, capabilities=["text.summarize"], policies=[])
        provider = _CostProvider(0.04)
        outcomes = []
        with chdir(root):
            agent = instantiate_agent(DigestAgent, llm=provider, root=root, config=cfg)
            for _ in range(3):
                try:
                    agent.run(DigestAgentInput(query="summarize"))
                    outcomes.append("ok")
                except BudgetExceeded:
                    outcomes.append("BudgetExceeded")
            spend = SqliteAuditLogger(root).total_cost(_AGENT)
    ok = outcomes == ["ok", "ok", "BudgetExceeded"]
    body = (
        "CASE 07-accrual-circuit-breaker: budget=0.05, cost=0.04/run, 3 runs.\n"
        f"outcomes={outcomes} (expect ['ok','ok','BudgetExceeded']) final_spend=${spend:.4f}\n"
        "run that crosses the budget completes; the next is blocked (one-run overshoot, sequential).\n"
        f"RESULT: {'PASS' if ok else 'FAIL'}\n"
    )
    (OUTPUTS / "case-07-accrual.out.txt").write_text(body, encoding="utf-8")
    print(f"[{'PASS' if ok else 'FAIL'}] case 07-accrual-circuit-breaker: outcomes={outcomes}")
    return ok


def _run_audit_cli() -> bool:
    """Case 08: seed an ok + a budget_exceeded row in a persistent project; render `lottie audit`."""
    demo = OUTPUTS / "audit-demo"
    demo.mkdir(parents=True, exist_ok=True)
    (demo / "lottie.yaml").write_text(
        "project: cost-demo\nproviders:\n  default: cost/sim\n", encoding="utf-8"
    )
    db = demo / ".lottie" / "audit.db"
    if db.exists():
        db.unlink()
    os.environ.pop("LOTTIE_DISABLE_AUDIT", None)
    with chdir(demo):
        # an ok run (under budget) ...
        provider = _CostProvider(0.01)
        instantiate_agent(
            DigestAgent, llm=provider, root=demo,
            config=_config(1.0, capabilities=["text.summarize"], policies=[]),
        ).run(DigestAgentInput(query="ok run"))
        # ... then an over-budget block.
        _seed(demo, 0.50)
        try:
            instantiate_agent(
                DigestAgent, llm=_CostProvider(0.0), root=demo,
                config=_config(0.50, capabilities=["text.summarize"], policies=[]),
            ).run(DigestAgentInput(query="blocked run"))
        except BudgetExceeded:
            pass
        statuses = {r.status for r in SqliteAuditLogger(demo).query(limit=20)}
        cli = subprocess.run(
            [str(Path(sys.executable).parent / "lottie"), "audit"],
            capture_output=True, text=True, cwd=demo,
        )
    out = cli.stdout + cli.stderr
    (OUTPUTS / "case-08-audit.out.txt").write_text(
        f"CASE 08-audit-integration: ok + budget_exceeded rows + `lottie audit` render.\n"
        f"audit statuses present: {sorted(statuses)}\nlottie audit exit={cli.returncode}\n\n{out}\n",
        encoding="utf-8",
    )
    ok = {"ok", "budget_exceeded"} <= statuses and cli.returncode == 0
    print(f"[{'PASS' if ok else 'FAIL'}] case 08-audit-integration: statuses={sorted(statuses)}")
    return ok


def main() -> int:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    results = [_run_case(c) for c in CASES]
    results.append(_run_accrual())
    results.append(_run_audit_cli())
    passed = sum(results)
    total = len(results)
    print(f"\nRESULT: {passed}/{total} cases PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
