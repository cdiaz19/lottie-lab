"""Round-35 reflect-module driver — validate orchestrator E4 S2 from downstream.

Reflection left `BaseAgent` and became a module in the memory subsystem. The behaviour
must be identical: opt-in, success-only, budget-respecting, and never able to fail an
already-successful run.

Case 4 is the load-bearing one. Reflection SPENDS TOKENS, so "skip when the run's cap is
already reached" is the property that keeps learning from being the thing that overspends.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

from lottie.core.middleware import build_chain
from lottie.llm import MockLLMProvider
from lottie.memory.middleware import ReflectMiddleware
from lottie.memory.schema import MemoryQuery, MemoryTier
from lottie.memory.store import SqliteMemoryClient
from lottie.project.config import AgentConfig
from lottie.project.discovery import instantiate_agent

from agents.digest.agent import DigestAgent
from agents.digest.schema import DigestAgentInput

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent
_SCRATCH = Path(tempfile.mkdtemp(prefix="round35-"))
_SEQ = iter(range(1000))

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def _db() -> Path:
    return _SCRATCH / f"m-{next(_SEQ)}.db"


def _agent(db: Path | None = None, *, reflect: bool = False, **extra: object) -> DigestAgent:
    cfg: dict[str, object] = {"provider": "mock/sim", **extra}
    if db is not None:
        cfg["memory"] = {
            "enabled": True,
            "backend": "sqlite",
            "path": str(db),
            "namespace": "r35",
            "reflect": {"enabled": reflect},
        }
    return instantiate_agent(  # type: ignore[return-value]
        DigestAgent,
        llm=MockLLMProvider(["an answer", "- prefer exponential backoff"] * 3),
        root=LAB_ROOT,
        config=AgentConfig.model_validate(cfg),
        enable_benchmarks=False,
    )


def _semantic(db: Path) -> list[str]:
    if not db.exists():
        return []
    hits = SqliteMemoryClient(db).recall(
        MemoryQuery(text="", namespace="r35", tier=MemoryTier.SEMANTIC, limit=50)
    ).hits
    return [h.record.content for h in hits]


try:
    # --- Case 1: ownership ---------------------------------------------------
    owner = {m.name: type(m).__module__ for m in build_chain(_agent())}.get("reflect")
    check(
        "1. reflect is owned by the memory subsystem",
        owner == "lottie.memory.middleware",
        f"owner={owner}",
    )

    # --- Case 2: OFF by default ---------------------------------------------
    db = _db()
    _agent(db).run(DigestAgentInput(query="alpha"))
    check("2. reflection is still OFF by default", _semantic(db) == [])

    # --- Case 3: enabled, it writes a lesson --------------------------------
    db = _db()
    _agent(db, reflect=True).run(DigestAgentInput(query="alpha"))
    notes = _semantic(db)
    check(
        "3. enabled, a successful run writes a SEMANTIC lesson",
        len(notes) == 1 and "backoff" in notes[0],
        f"notes={len(notes)}",
    )

    # --- Case 4: skip-when-exhausted ----------------------------------------
    # Reflection SPENDS TOKENS. This is the property that keeps learning from being the
    # thing that overspends a run's budget.
    #
    # The cap is 0, not 1, on purpose: MockLLMProvider reports zero usage, so a run's
    # spend never climbs and a cap of 1 would never be reached. A cap of 0 means "this
    # run has no token budget at all", which is a real configuration and does trigger the
    # guard end-to-end.
    db = _db()
    capped = _agent(db, reflect=True, max_run_tokens=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            capped.run(DigestAgentInput(query="alpha"))
        except Exception:
            pass
    check(
        "4. reflection is SKIPPED when the run's token cap is already reached",
        _semantic(db) == [],
        f"notes={len(_semantic(db))}",
    )

    # --- Case 5: a failed run is not reflected on ---------------------------
    # A failure has no outcome to learn from.
    db = _db()
    failing = _agent(db, reflect=True)
    try:
        failing.run(DigestAgentInput(query="   "))
    except ValueError:
        pass
    check("5. a FAILED run is never reflected on", _semantic(db) == [])

    # --- Case 6: reflection cannot fail an already-successful run ----------
    db = _db()
    broken = _agent(db, reflect=True)

    def _boom(messages: list[object]) -> str:
        raise RuntimeError("reflector down")

    broken._budgeted_call = _boom  # type: ignore[method-assign]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = broken.run(DigestAgentInput(query="alpha"))
    check(
        "6. a reflector failure never fails an already-successful run",
        out.result == "an answer" and _semantic(db) == [],
        f"result={out.result!r}",
    )

    # --- Case 7: the lesson lands in SEMANTIC, not EPISODIC ----------------
    # Tier follows origin: a reflection lesson is a note, a trajectory is an event.
    db = _db()
    _agent(db, reflect=True).run(DigestAgentInput(query="alpha"))
    episodic = SqliteMemoryClient(db).recall(
        MemoryQuery(text="", namespace="r35", tier=MemoryTier.EPISODIC, limit=50)
    ).hits
    check(
        "7. the lesson lands in SEMANTIC and not EPISODIC (tier follows origin)",
        len(_semantic(db)) == 1 and episodic == [],
        f"semantic={len(_semantic(db))}, episodic={len(episodic)}",
    )

    # --- Case 8: the module constructs without an agent --------------------
    # The BudgetedCaller protocol is the whole coupling it actually needed.
    standalone = ReflectMiddleware(
        lambda messages: "- a lesson",
        lambda deltas, ns, origin: None,
        lambda: None,
        enabled=True,
        namespace="ns",
        max_run_tokens=None,
    )
    check(
        "8. ReflectMiddleware constructs from callables alone, with no agent",
        standalone.name == "reflect",
        "no BaseAgent in its constructor",
    )

finally:
    shutil.rmtree(_SCRATCH, ignore_errors=True)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "35",
            "slice": "E4 S2 — reflection as a module",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
