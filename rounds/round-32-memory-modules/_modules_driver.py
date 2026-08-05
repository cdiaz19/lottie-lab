"""Round-32 memory-module driver — validate orchestrator V3 S5 from downstream.

S5 moved recall, trajectory and session out of `core` into their owning subsystems, with
the LOGIC moving rather than just the class. Behaviour must be identical.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from lottie.core.middleware import build_chain
from lottie.llm import MockLLMProvider
from lottie.memory.schema import MemoryQuery, MemoryTier
from lottie.memory.store import SqliteMemoryClient
from lottie.project.config import AgentConfig
from lottie.project.discovery import instantiate_agent
from lottie.session.store import SessionStore

from agents.digest.agent import DigestAgent
from agents.digest.schema import DigestAgentInput

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent
_SCRATCH = Path(tempfile.mkdtemp(prefix="round32-"))
_SEQ = iter(range(1000))

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def _db() -> Path:
    return _SCRATCH / f"m-{next(_SEQ)}.db"


def _agent(db: Path | None = None, **memory: object) -> DigestAgent:
    cfg: dict[str, object] = {"provider": "mock/sim"}
    if memory:
        cfg["memory"] = {
            "enabled": True,
            "backend": "sqlite",
            "path": str(db),
            "namespace": "r32",
            **memory,
        }
    return instantiate_agent(  # type: ignore[return-value]
        DigestAgent,
        llm=MockLLMProvider(["an answer"] * 4),
        root=LAB_ROOT,
        config=AgentConfig.model_validate(cfg),
        enable_benchmarks=False,
    )


try:
    # --- Case 1: ownership -------------------------------------------------
    owners = {m.name: type(m).__module__ for m in build_chain(_agent())}
    check(
        "1. recall / trajectory / session are owned by their subsystems",
        owners.get("recall") == "lottie.memory.middleware"
        and owners.get("trajectory") == "lottie.memory.middleware"
        and owners.get("session") == "lottie.session.middleware",
        f"recall={owners.get('recall')}, session={owners.get('session')}",
    )

    # --- Case 2: the chain is still complete -------------------------------
    chain = build_chain(_agent())
    check(
        "2. the chain is 11 modules with distinct orders (audit left in S4)",
        len(chain) == 11 and len({m.order for m in chain}) == 11,
        f"modules={len(chain)}",
    )

    # --- Case 3: trajectory capture still works ----------------------------
    db = _db()
    agent = _agent(db, trajectory={"enabled": True})
    agent.run(DigestAgentInput(query="alpha"))
    hits = SqliteMemoryClient(db).recall(
        MemoryQuery(text="", namespace="r32", tier=MemoryTier.EPISODIC, limit=10)
    ).hits
    check(
        "3. episodic trajectory capture still works after the move",
        len(hits) == 1,
        f"episodic={len(hits)}",
    )

    # --- Case 4: still OFF by default --------------------------------------
    db = _db()
    _agent(db).run(DigestAgentInput(query="beta"))
    check(
        "4. trajectory is still OFF by default",
        not db.exists()
        or SqliteMemoryClient(db)
        .recall(MemoryQuery(text="", namespace="r32", tier=MemoryTier.EPISODIC, limit=10))
        .hits
        == [],
    )

    # --- Case 5: recall still injects as DATA ------------------------------
    db = _db()
    seeded = _agent(db, recall={"enabled": True})
    from lottie.memory.schema import MemoryOrigin, MemoryRecord

    SqliteMemoryClient(db).remember(
        MemoryRecord(
            content="prefer exponential backoff",
            tier=MemoryTier.SEMANTIC,
            namespace="r32",
            origin=MemoryOrigin.REFLECTION,
        )
    )
    seeded.run(DigestAgentInput(query="q"))
    sent = seeded.llm.calls[-1]  # type: ignore[attr-defined]
    check(
        "5. recall still injects the note as a DATA block (S2a contract)",
        any("recalled-notes" in m.content for m in sent),
        "render_as_data block present",
    )

    # --- Case 6: the prefix does not leak between runs ---------------------
    check(
        "6. the recall prefix is cleared after the run",
        seeded._recall_prefix == "",
        f"prefix={seeded._recall_prefix!r}",
    )

    # --- Case 7: sessions still persist and resume -------------------------
    store = SessionStore(_SCRATCH)
    a = _agent()
    a.set_session(store, "s1")
    a.run(DigestAgentInput(query="one"))
    b = _agent()
    b.set_session(store, "s1")
    b.run(DigestAgentInput(query="two"))
    state = store.require("s1")
    check(
        "7. session history still accumulates across fresh agents",
        len(state.runs) == 2,
        f"runs={len(state.runs)}",
    )

    # --- Case 8: session history is still hash-only ------------------------
    check(
        "8. session run history is still hash-only",
        all(r.input_sha256 and len(r.input_sha256) == 64 for r in state.runs),
        "input_sha256 present on every run",
    )

    # --- Case 9: a failed run is still recorded ----------------------------
    c = _agent()
    c.set_session(store, "s2")
    try:
        c.run(DigestAgentInput(query="   "))
    except ValueError:
        pass
    check(
        "9. a failed run is still recorded in the session as an error",
        store.require("s2").runs[0].status == "error",
        f"status={store.require('s2').runs[0].status}",
    )

finally:
    shutil.rmtree(_SCRATCH, ignore_errors=True)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "32",
            "slice": "V3 S5 — memory and session modules",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
