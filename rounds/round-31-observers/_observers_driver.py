"""Round-31 observers driver — validate orchestrator V3 S4 from downstream.

S4 took auditing out of the middleware chain and made it an `EventBus` subscriber. The
claim is that "best-effort" stops being a convention each observer must remember and
becomes a property of the bus.

Case 6 is the one that would have caught the regression this slice actually introduced:
a stream cancelled by the transport must be audited as PARTIAL, not "ok".
"""

from __future__ import annotations

import json
import sys
import tempfile
import warnings
from collections.abc import Iterator
from pathlib import Path

from lottie.core.middleware import build_chain
from lottie.governance.audit import SqliteAuditLogger
from lottie.governance.policy import PolicyDenied, PolicyGate
from lottie.governance.subscribers import AuditSubscriber
from lottie.llm import MockLLMProvider
from lottie.project.config import AgentConfig
from lottie.project.discovery import instantiate_agent
from lottie.runtime.events import EventBus, RunEvent

from agents.digest.agent import DigestAgent
from agents.digest.schema import DigestAgentInput

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent
_SCRATCH = Path(tempfile.mkdtemp(prefix="round31-"))
_SEQ = iter(range(1000))

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def _ledger() -> Path:
    return _SCRATCH / f"a-{next(_SEQ)}.db"


class _Streaming(DigestAgent):
    def _stream(self, data: DigestAgentInput) -> Iterator[str]:
        yield from ("alpha ", "beta ", "gamma")


def _agent(cls: type = DigestAgent, ledger: Path | None = None) -> DigestAgent:
    agent = instantiate_agent(  # type: ignore[return-value]
        cls,
        llm=MockLLMProvider(["an answer"] * 4),
        root=LAB_ROOT,
        config=AgentConfig.model_validate({"provider": "mock/sim"}),
        enable_benchmarks=False,
    )
    if ledger is not None:
        agent._audit = SqliteAuditLogger(ledger)
    return agent


# --- Case 1: audit is no longer in the chain --------------------------------
names = {m.name for m in build_chain(_agent())}
check(
    "1. audit is no longer a middleware — it is an observer",
    "audit" not in names,
    f"chain={sorted(names)}",
)

# --- Case 2: a successful run is still audited root=True --------------------
ledger = _ledger()
_agent(ledger=ledger).run(DigestAgentInput(query="q"))
rows = SqliteAuditLogger(ledger).query()
check(
    "2. a successful run is still audited, still root=True",
    len(rows) == 1 and rows[0].status == "ok" and rows[0].root is True,
    f"rows={len(rows)}, status={rows[0].status if rows else None}",
)

# --- Case 3: the record still carries hashes and usage ----------------------
row = rows[0]
check(
    "3. the record still carries the input hash, provider and timing",
    row.input_sha256 is not None
    and len(row.input_sha256) == 64
    and row.provider is not None
    and row.latency_ms >= 0.0,
    f"provider={row.provider}",
)

# --- Case 4: a failed run is audited status=error ---------------------------
ledger = _ledger()
failing = _agent(ledger=ledger)
try:
    failing.run(DigestAgentInput(query="   "))
except ValueError:
    pass
rows = SqliteAuditLogger(ledger).query()
check(
    "4. a failed run is audited status=error with the message",
    len(rows) == 1 and rows[0].status == "error" and rows[0].error,
    f"status={rows[0].status if rows else None}",
)

# --- Case 5: a completed stream is audited ----------------------------------
ledger = _ledger()
streamer = _agent(_Streaming, ledger=ledger)
list(streamer.run_stream(DigestAgentInput(query="q")))
rows = SqliteAuditLogger(ledger).query()
check(
    "5. a completed stream is audited with no output hash",
    len(rows) == 1 and rows[0].status == "ok" and rows[0].output_sha256 is None,
    f"status={rows[0].status if rows else None}",
)

# --- Case 6: a CANCELLED stream is audited PARTIAL, not "ok" ---------------
# The regression this slice actually introduced and a pre-existing test caught:
# GeneratorExit is a BaseException, so an `except Exception` misses it and the run
# would be recorded successful. A cancelled request must never look like a clean one.
ledger = _ledger()
cancelled = _agent(_Streaming, ledger=ledger)
stream = cancelled.run_stream(DigestAgentInput(query="q"))
next(stream)
stream.close()
rows = SqliteAuditLogger(ledger).query()
check(
    "6. a CANCELLED stream is audited as partial, never as ok",
    len(rows) == 1
    and rows[0].status == "error"
    and rows[0].error == "stream closed before completion",
    f"status={rows[0].status if rows else None}, error={rows[0].error if rows else None!r}",
)

# --- Case 7: blocked runs still audited by the gate, not the bus ------------
ledger = _ledger()
denied = _agent(ledger=ledger)
denied.set_policy(PolicyGate(["banned"], allow=set(), deny={"banned"}, escalate=set()))
try:
    denied.run(DigestAgentInput(query="q"))
except PolicyDenied:
    pass
rows = SqliteAuditLogger(ledger).query()
check(
    "7. a denied run keeps its governance-specific status (gate audits it, not the bus)",
    len(rows) == 1 and rows[0].status == "denied" and rows[0].root is True,
    f"status={rows[0].status if rows else None}",
)

# --- Case 8: a SABOTAGING observer cannot fail a run -----------------------
# The whole point of making audit a subscriber: best-effort is structural now.
class _Sabotage:
    name = "sabotage"

    def on_event(self, event: RunEvent) -> None:
        raise RuntimeError("observer sabotage")


ledger = _ledger()
sabotaged = _agent(ledger=ledger)
original_build = sabotaged._build_pipeline


def _with_saboteur():  # type: ignore[no-untyped-def]
    pipe = original_build()
    pipe._bus.subscribe(_Sabotage())
    return pipe


sabotaged._build_pipeline = _with_saboteur  # type: ignore[method-assign]
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    out = sabotaged.run(DigestAgentInput(query="q"))
rows = SqliteAuditLogger(ledger).query()
check(
    "8. a sabotaging observer cannot fail the run, and audit still lands",
    out.result == "an answer" and len(rows) == 1,
    f"result={out.result!r}, audited={len(rows)}",
)

# --- Case 9: the subscriber is reusable standalone -------------------------
# It takes a logger and reads everything off the event — no agent coupling.
ledger = _ledger()
bus = EventBus()
bus.subscribe(AuditSubscriber(SqliteAuditLogger(ledger)))
check(
    "9. AuditSubscriber constructs from a logger alone, with no agent",
    True,
    "no BaseAgent in its constructor",
)

import shutil

shutil.rmtree(_SCRATCH, ignore_errors=True)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "31",
            "slice": "V3 S4 — observers as subscribers",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
