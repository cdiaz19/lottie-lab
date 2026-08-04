"""Round-29b streaming-chain driver — validate orchestrator V3 S2b from downstream.

S2b put `run_stream` on the same middleware instances `run()` uses, removing the last
hand-sequenced execution path. The interesting property is TEMPORAL: a scope must span
generator CONSUMPTION, not generator creation. Under the plain middleware contract a
`finally` fires when the generator object is made, settling the budget before a single
delta exists.

Cases 4-7 are the ones that would catch that regression.
"""

from __future__ import annotations

import json
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

from lottie.core.base_agent import _depth
from lottie.governance.audit import SqliteAuditLogger
from lottie.governance.capability import CapabilityGate, active_capability_gate
from lottie.governance.policy import PolicyDenied, PolicyGate
from lottie.llm import MockLLMProvider
from lottie.project.config import AgentConfig
from lottie.project.discovery import instantiate_agent

from agents.digest.agent import DigestAgent
from agents.digest.schema import DigestAgentInput

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent
_SCRATCH = Path(tempfile.mkdtemp(prefix="round29b-"))
_SEQ = iter(range(1000))

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def _ledger() -> Path:
    return _SCRATCH / f"audit-{next(_SEQ)}.db"


class _Streaming(DigestAgent):
    """DigestAgent already implements `_stream`; this records when deltas are produced."""

    log: list[str] = []

    def _stream(self, data: DigestAgentInput) -> Iterator[str]:
        for piece in ("alpha ", "beta ", "gamma"):
            type(self).log.append(f"yield:{piece.strip()}")
            yield piece


def _agent(**cfg: object) -> _Streaming:
    _Streaming.log = []
    return instantiate_agent(  # type: ignore[return-value]
        _Streaming,
        llm=MockLLMProvider(["x"] * 4),
        root=LAB_ROOT,
        config=AgentConfig.model_validate({"provider": "mock/sim", **cfg}),
        enable_benchmarks=False,
    )


# --- Case 1: the streaming chain is the scoped subset -----------------------
names = _agent()._build_pipeline().scoped_names()
check(
    "1. the streaming chain is exactly policy, cost, audit, depth, capability",
    names == ["policy", "cost", "audit", "depth", "capability"],
    f"names={names}",
)

# --- Case 2: output-shaping middleware are absent ---------------------------
check(
    "2. verify / security_output / reflect are absent (a stream has no Output)",
    not {"verify", "security_output", "reflect"} & set(names),
)

# --- Case 3: deltas reach the caller ----------------------------------------
pieces = list(_agent().run_stream(DigestAgentInput(query="q")))
check(
    "3. deltas reach the caller unchanged",
    pieces == ["alpha ", "beta ", "gamma"],
    f"pieces={pieces}",
)

# --- Case 4: an unconsumed generator does NOTHING ---------------------------
agent = _agent()
agent.run_stream(DigestAgentInput(query="q"))  # never iterated
check(
    "4. an unconsumed stream generator runs no gates and produces no deltas",
    _Streaming.log == [],
    f"log={_Streaming.log}",
)

# --- Case 5: audit fires AFTER the last delta, not at generator creation ----
# This is the regression ScopedMiddleware exists to prevent.
ledger = _ledger()
agent = _agent()
agent._audit = SqliteAuditLogger(ledger)
stream = agent.run_stream(DigestAgentInput(query="q"))
first = next(stream)
mid_records = SqliteAuditLogger(ledger).query(agent=None, since=None, limit=10)
list(stream)  # drain
final_records = SqliteAuditLogger(ledger).query(agent=None, since=None, limit=10)
check(
    "5. audit fires only after the last delta, never at generator creation",
    first == "alpha " and len(mid_records) == 0 and len(final_records) == 1,
    f"mid={len(mid_records)}, final={len(final_records)}",
)

# --- Case 6: the capability gate is live INSIDE _stream ---------------------
seen: list[object] = []


class _CapStream(_Streaming):
    def _stream(self, data: DigestAgentInput) -> Iterator[str]:
        seen.append(active_capability_gate())
        yield "only"


capped = instantiate_agent(
    _CapStream,
    llm=MockLLMProvider(["x"]),
    root=LAB_ROOT,
    config=AgentConfig.model_validate({"provider": "mock/sim", "capabilities": ["retrieval"]}),
    enable_benchmarks=False,
)
list(capped.run_stream(DigestAgentInput(query="q")))
check(
    "6. the rule-11 gate is active for the whole stream, not just its creation",
    seen and seen[0] is capped._capabilities,
    "gate live inside _stream",
)

# --- Case 7: closing early still unwinds every scope ------------------------
# The 3b transport cancels by closing the generator; the reservation must still settle
# and the depth counter must still be restored.
ledger = _ledger()
agent = _agent()
agent._audit = SqliteAuditLogger(ledger)
stream = agent.run_stream(DigestAgentInput(query="q"))
next(stream)
stream.close()
check(
    "7. closing the stream early still unwinds the scopes (audit written, depth restored)",
    len(SqliteAuditLogger(ledger).query(agent=None, since=None, limit=10)) == 1
    and _depth() == 0,
    f"depth={_depth()}",
)

# --- Case 8: a denied stream raises before the first delta ------------------
denied = _agent()
denied.set_policy(PolicyGate(["banned"], allow=set(), deny={"banned"}, escalate=set()))
blocked = False
try:
    next(denied.run_stream(DigestAgentInput(query="q")))
except PolicyDenied:
    blocked = True
check(
    "8. a policy-denied stream raises before any delta is produced",
    blocked and _Streaming.log == [],
    f"blocked={blocked}, deltas={_Streaming.log}",
)

# --- Case 9: non-streaming runs are unaffected ------------------------------
out = _agent().run(DigestAgentInput(query="q"))
check(
    "9. the non-streaming path still works alongside the shared chain",
    out.result == "x",
    f"result={out.result!r}",
)

import shutil

shutil.rmtree(_SCRATCH, ignore_errors=True)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "29b",
            "slice": "V3 S2b — streaming chain",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
