"""Round-29 pipeline swap-in driver — validate orchestrator V3 S2a from downstream.

S2a rewired `BaseAgent.run` from a hand-sequenced list of cross-cutting steps into one
line over a middleware chain. The claim is **behaviour preservation**, so this round
drives a REAL lab agent through the real `instantiate_agent` path and checks that the
governance guarantees a downstream project depends on are all still intact.

Cases 5-8 target the three orderings S2a identified as load-bearing — the ones where a
wrong position would change security or audit semantics silently.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from lottie.core.middleware import build_chain
from lottie.governance.audit import SqliteAuditLogger
from lottie.governance.capability import CapabilityDenied, active_capability_gate
from lottie.governance.policy import PolicyDenied, PolicyGate
from lottie.llm import MockLLMProvider
from lottie.project.config import AgentConfig
from lottie.project.discovery import instantiate_agent

from agents.digest.agent import DigestAgent
from agents.digest.schema import DigestAgentInput

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent
_SCRATCH = Path(tempfile.mkdtemp(prefix="round29-"))
_LEDGER_SEQ = iter(range(1000))

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def _fresh_ledger() -> Path:
    """A brand-new ledger file per case.

    A new path rather than deleting the old one: the sandbox this runs in forbids
    unlink, and an empty ledger is what the assertions actually need.
    """
    return _SCRATCH / f"audit-{next(_LEDGER_SEQ)}.db"


def _agent(cls: type = DigestAgent, **cfg: object) -> DigestAgent:
    return instantiate_agent(  # type: ignore[return-value]
        cls,
        llm=MockLLMProvider(["an answer"] * 6),
        root=LAB_ROOT,
        config=AgentConfig.model_validate({"provider": "mock/sim", **cfg}),
        enable_benchmarks=False,
    )


try:
    # --- Case 1: an ordinary run still works --------------------------------
    out = _agent().run(DigestAgentInput(query="what is a mesh"))
    check(
        "1. an ordinary agent run is unchanged after the swap-in",
        out.result == "an answer",
        f"result={out.result!r}",
    )

    # --- Case 2: the whole standard chain is mounted ------------------------
    # S3 replaced STANDARD_CHAIN with build_chain(agent); S4 moved audit out of the
    # chain to become an EventBus subscriber, so the count is 11 rather than 12.
    chain = build_chain(_agent())
    orders = [m.order for m in chain]
    check(
        "2. the standard middleware mount with distinct orders",
        len(chain) == 11 and len(set(orders)) == 11,
        f"mounted={len(chain)}, distinct_orders={len(set(orders))}",
    )

    # --- Case 3: audit still records a root run -----------------------------
    ledger = _fresh_ledger()
    audited = instantiate_agent(
        DigestAgent,
        llm=MockLLMProvider(["x"]),
        root=LAB_ROOT,
        config=AgentConfig.model_validate({"provider": "mock/sim"}),
        enable_benchmarks=False,
    )
    audited._audit = SqliteAuditLogger(ledger)
    audited.run(DigestAgentInput(query="audit me"))
    records = SqliteAuditLogger(ledger).query(agent=None, since=None, limit=50)
    check(
        "3. the run is still audited, and still flagged root",
        len(records) == 1 and records[0].root is True and records[0].status == "ok",
        f"records={len(records)}, root={records[0].root if records else None}",
    )

    # --- Case 4: a failed run is audited as an error ------------------------
    ledger = _fresh_ledger()
    failing = instantiate_agent(
        DigestAgent,
        llm=MockLLMProvider(["x"]),
        root=LAB_ROOT,
        config=AgentConfig.model_validate({"provider": "mock/sim"}),
        enable_benchmarks=False,
    )
    failing._audit = SqliteAuditLogger(ledger)
    try:
        failing.run(DigestAgentInput(query="   "))  # DigestAgent rejects a blank query
    except ValueError:
        pass
    records = SqliteAuditLogger(ledger).query(agent=None, since=None, limit=50)
    check(
        "4. a failed run is still audited with status=error",
        len(records) == 1 and records[0].status == "error",
        f"status={records[0].status if records else None}",
    )

    # --- Case 5: a DENIED run is still audited root=True --------------------
    # The reason DEPTH sits above COST: `_write_block` reads `_depth() == 0`, so a depth
    # middleware running before the gates would mislabel a denied top-level run.
    ledger = _fresh_ledger()
    denied = instantiate_agent(
        DigestAgent,
        llm=MockLLMProvider(["x"]),
        root=LAB_ROOT,
        config=AgentConfig.model_validate({"provider": "mock/sim"}),
        enable_benchmarks=False,
    )
    denied._audit = SqliteAuditLogger(ledger)
    # Gate set directly rather than via a policy file: the assertion is about the audit
    # root flag on a denied run, not about policy loading.
    denied.set_policy(
        PolicyGate(["banned"], allow=set(), deny={"banned"}, escalate=set())
    )
    blocked = False
    try:
        denied.run(DigestAgentInput(query="denied"))
    except PolicyDenied:
        blocked = True
    records = SqliteAuditLogger(ledger).query(agent=None, since=None, limit=50)
    root_ok = bool(records) and records[0].root is True and records[0].status == "denied"
    check(
        "5. a policy-denied run is audited status=denied AND root=True",
        blocked and root_ok,
        f"blocked={blocked}, status={records[0].status if records else None}, "
        f"root={records[0].root if records else None}",
    )

    # --- Case 6: the capability gate is active during _execute --------------
    seen_in_execute: list[object] = []

    class _CapProbe(DigestAgent):
        def _execute(self, data: DigestAgentInput) -> object:  # type: ignore[override]
            seen_in_execute.append(active_capability_gate())
            return super()._execute(data)

    capped = _agent(_CapProbe, capabilities=["retrieval"])
    capped.run(DigestAgentInput(query="q"))
    check(
        "6. the rule-11 capability gate is active during _execute",
        seen_in_execute and seen_in_execute[0] is capped._capabilities,
        "gate active inside the execute window",
    )

    # --- Case 7: the gate is ALREADY RELEASED during _verify ----------------
    # This is why CAPABILITY is the innermost middleware. `_verify` is user code that may
    # call a skill, and today it runs with the gate reset. Any other position would
    # silently change rule-11 enforcement there.
    seen_in_verify: list[object] = []

    class _VerifyProbe(DigestAgent):
        def _verify(self, data: DigestAgentInput, output: object) -> None:
            seen_in_verify.append(active_capability_gate())

    verified = _agent(_VerifyProbe, capabilities=["retrieval"])
    verified.run(DigestAgentInput(query="q"))
    check(
        "7. the capability gate is already released during _verify",
        seen_in_verify and seen_in_verify[0] is not verified._capabilities,
        "gate released before the verify hook",
    )

    # --- Case 8: an undeclared skill call is still blocked ------------------
    from lottie.core import BaseSkill
    from pydantic import BaseModel

    class _SkillIn(BaseModel):
        x: str

    class _SkillOut(BaseModel):
        y: str

    class ForbiddenSkill(BaseSkill[_SkillIn, _SkillOut]):
        def _execute(self, data: _SkillIn) -> _SkillOut:
            return _SkillOut(y=data.x)

    class _SkillCaller(DigestAgent):
        def _execute(self, data: DigestAgentInput) -> object:  # type: ignore[override]
            ForbiddenSkill(enable_benchmarks=False).run(_SkillIn(x="boom"))
            return super()._execute(data)

    caller = _agent(_SkillCaller, capabilities=["retrieval"])
    denied_skill = False
    try:
        caller.run(DigestAgentInput(query="q"))
    except CapabilityDenied:
        denied_skill = True
    check(
        "8. rule 11 still blocks an undeclared skill call inside _execute",
        denied_skill,
        "CapabilityDenied raised",
    )

    # --- Case 9: _verify still fails a run closed ---------------------------
    class _Rejecting(DigestAgent):
        def _verify(self, data: DigestAgentInput, output: object) -> None:
            raise ValueError("post-condition failed")

    rejected = False
    try:
        _agent(_Rejecting).run(DigestAgentInput(query="q"))
    except ValueError:
        rejected = True
    check("9. the _verify post-condition still fails a run closed", rejected)

finally:
    shutil.rmtree(_SCRATCH, ignore_errors=True)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "29",
            "slice": "V3 S2a — pipeline swap-in",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
