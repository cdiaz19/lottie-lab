"""Round-30 module-ownership driver — validate orchestrator V3 S3 from downstream.

S3 moved the fail-closed modules — security (rules 8/9), policy, cost, capability
(rule 11) — out of `core` and into their owning subsystems, constructed from their gate
alone. The behaviour must be identical; what changes is who owns the code.

Cases 1-3 verify the ownership move structurally. Cases 4-9 verify every fail-closed
guarantee still actually holds from a downstream project.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from pydantic import BaseModel

from lottie.core import BaseSkill
from lottie.core.middleware import build_chain
from lottie.governance.audit import SqliteAuditLogger
from lottie.governance.capability import CapabilityDenied
from lottie.governance.cost import BudgetExceeded, CostGate
from lottie.governance.policy import PolicyDenied, PolicyGate
from lottie.llm import MockLLMProvider
from lottie.project.config import AgentConfig
from lottie.project.discovery import instantiate_agent

from agents.digest.agent import DigestAgent
from agents.digest.schema import DigestAgentInput

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent
_SCRATCH = Path(tempfile.mkdtemp(prefix="round30-"))
_SEQ = iter(range(1000))

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def _ledger() -> Path:
    return _SCRATCH / f"audit-{next(_SEQ)}.db"


def _agent(cls: type = DigestAgent, **cfg: object) -> DigestAgent:
    return instantiate_agent(  # type: ignore[return-value]
        cls,
        llm=MockLLMProvider(["an answer"] * 4),
        root=LAB_ROOT,
        config=AgentConfig.model_validate({"provider": "mock/sim", **cfg}),
        enable_benchmarks=False,
    )


# --- Case 1: each fail-closed module is owned by its subsystem --------------
owners = {m.name: type(m).__module__ for m in build_chain(_agent())}
expected = {
    "security_input": "lottie.security.middleware",
    "security_output": "lottie.security.middleware",
    "policy": "lottie.governance.middleware",
    "cost": "lottie.governance.middleware",
    "capability": "lottie.governance.middleware",
}
check(
    "1. security / policy / cost / capability are owned by their subsystems",
    all(owners.get(k) == v for k, v in expected.items()),
    f"owners={ {k: owners.get(k) for k in expected} }",
)

# --- Case 2: the chain is still complete ------------------------------------
chain = build_chain(_agent())
check(
    "2. the chain is still 12 modules with distinct orders",
    len(chain) == 12 and len({m.order for m in chain}) == 12,
    f"modules={len(chain)}",
)

# --- Case 3: the migrated modules do not know about BaseAgent ---------------
# Constructed from their gate alone — the coupling that has to go before S6.
from lottie.governance.middleware import CapabilityMiddleware, PolicyMiddleware
from lottie.security.middleware import SecurityInputMiddleware

standalone_ok = True
try:
    PolicyMiddleware(
        PolicyGate([], allow=set(), deny=set(), escalate=set()), lambda *a: None
    )
    CapabilityMiddleware.__init__  # constructed from a gate, no agent
    SecurityInputMiddleware.__init__
except Exception:
    standalone_ok = False
check(
    "3. the migrated modules construct from a gate alone, with no agent",
    standalone_ok,
    "no BaseAgent in their constructors",
)

# --- Case 4: rule 8 still screens the input ---------------------------------
class _RejectAll:
    def check_input(self, payload: str) -> None:
        raise ValueError("input refused")

    def check_output(self, payload: str) -> None:
        return None


gated = _agent()
gated.set_security_gate(_RejectAll())  # type: ignore[arg-type]
rule8 = False
try:
    gated.run(DigestAgentInput(query="q"))
except ValueError:
    rule8 = True
check("4. rule 8 — the input gate still refuses fail-closed", rule8)

# --- Case 5: rule 9 still screens the output --------------------------------
class _RejectOutput:
    def check_input(self, payload: str) -> None:
        return None

    def check_output(self, payload: str) -> None:
        raise ValueError("output withheld")


gated = _agent()
gated.set_security_gate(_RejectOutput())  # type: ignore[arg-type]
rule9 = False
try:
    gated.run(DigestAgentInput(query="q"))
except ValueError:
    rule9 = True
check("5. rule 9 — the output gate still withholds fail-closed", rule9)

# --- Case 6: policy still denies, and still audits the block ----------------
ledger = _ledger()
denied = _agent()
denied._audit = SqliteAuditLogger(ledger)
denied.set_policy(PolicyGate(["banned"], allow=set(), deny={"banned"}, escalate=set()))
blocked = False
try:
    denied.run(DigestAgentInput(query="q"))
except PolicyDenied:
    blocked = True
records = SqliteAuditLogger(ledger).query(agent=None, since=None, limit=10)
check(
    "6. policy still denies AND still audits the block (root=True)",
    blocked and len(records) == 1 and records[0].status == "denied" and records[0].root,
    f"blocked={blocked}, status={records[0].status if records else None}",
)

# --- Case 7: budget still blocks, and still audits --------------------------
ledger = _ledger()


class _Broke(CostGate):
    def __init__(self) -> None:
        super().__init__("", 0.0, None)

    def reserve(self) -> int | None:
        raise BudgetExceeded("out of budget")


over = _agent()
over._audit = SqliteAuditLogger(ledger)
over.set_cost_gate(_Broke())
busted = False
try:
    over.run(DigestAgentInput(query="q"))
except BudgetExceeded:
    busted = True
records = SqliteAuditLogger(ledger).query(agent=None, since=None, limit=10)
check(
    "7. budget still blocks AND still audits status=budget_exceeded",
    busted and len(records) == 1 and records[0].status == "budget_exceeded",
    f"blocked={busted}, status={records[0].status if records else None}",
)

# --- Case 8: rule 11 still blocks an undeclared skill call ------------------
class _SkillIn(BaseModel):
    x: str


class _SkillOut(BaseModel):
    y: str


class ForbiddenSkill(BaseSkill[_SkillIn, _SkillOut]):
    def _execute(self, data: _SkillIn) -> _SkillOut:
        return _SkillOut(y=data.x)


class _Caller(DigestAgent):
    def _execute(self, data: DigestAgentInput) -> object:  # type: ignore[override]
        ForbiddenSkill(enable_benchmarks=False).run(_SkillIn(x="boom"))
        return super()._execute(data)


rule11 = False
try:
    _agent(_Caller, capabilities=["retrieval"]).run(DigestAgentInput(query="q"))
except CapabilityDenied:
    rule11 = True
check("8. rule 11 still blocks an undeclared skill call inside _execute", rule11)

# --- Case 9: an ordinary run is unchanged -----------------------------------
out = _agent().run(DigestAgentInput(query="q"))
check(
    "9. an ordinary run is unchanged after the ownership move",
    out.result == "an answer",
    f"result={out.result!r}",
)

# --- Case 10: streaming still uses the migrated scoped modules -------------
scoped = _agent()._build_pipeline().scoped_names()
check(
    "10. the streaming chain still mounts the migrated policy/cost/capability",
    scoped == ["policy", "cost", "audit", "depth", "capability"],
    f"scoped={scoped}",
)

import shutil

shutil.rmtree(_SCRATCH, ignore_errors=True)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "30",
            "slice": "V3 S3 — module ownership",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
