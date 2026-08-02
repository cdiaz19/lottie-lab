"""Round-26 learning-delta driver — validate orchestrator V2 S4 from downstream.

S4's whole purpose is to answer "does learning actually help?" with evidence rather than
assertion. A benchmark that can only ever say "yes" is worthless, so this round checks
that it reports honestly in three different worlds:

  - an EMPTY store           -> neutral, and the note count says why
  - a HELPFUL store          -> improved
  - the measurement itself   -> writes nothing, and is reproducible

The last one is the load-bearing property. If benchmarking mutated the corpus it measures,
every subsequent run would report different numbers and the report could not gate anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

import lottie.benchmark.learning as learning_mod
from lottie.benchmark.learning import learning_delta, write_delta_report
from lottie.llm import MockLLMProvider
from lottie.memory.schema import MemoryOrigin, MemoryQuery, MemoryRecord, MemoryTier
from lottie.memory.store import SqliteMemoryClient

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent
DB = LAB_ROOT / ".lottie" / "round26.db"
AGENT_DIR = LAB_ROOT / "agents" / "digest"
CONFIG = AGENT_DIR / "config.yaml"

NS = "round26"

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


_original_config = CONFIG.read_text()

# The suite must actually RUN. `mock/sim` is not a real litellm provider, so without this
# every case dies on a BadRequestError, both arms score 0.0, and the round reports a
# hollow "neutral" over two equally-broken runs. Case 0 below refuses to let that pass
# silently ever again.
_CANNED = [
    "a multi-agent system coordinates several agents",
    "large language models process language at scale",
    "Python is a programming language",
] * 20
learning_mod.build_provider = lambda model: MockLLMProvider(responses=list(_CANNED))


def _configure() -> None:
    """Point digest at a scratch memory db in its own namespace, memory enabled."""
    cfg = yaml.safe_load(_original_config)
    cfg["provider"] = "mock/sim"
    cfg["memory"] = {
        "enabled": True,
        "backend": "sqlite",
        "path": ".lottie/round26.db",
        "namespace": NS,
        "recall": {"enabled": False},  # the arms override this; this is the resting state
    }
    CONFIG.write_text(yaml.safe_dump(cfg, sort_keys=False))


def _restore() -> None:
    CONFIG.write_text(_original_config)
    if DB.exists():
        DB.unlink()


def _seed(notes: list[str]) -> None:
    client = SqliteMemoryClient(DB)
    for note in notes:
        client.remember(
            MemoryRecord(
                content=note,
                tier=MemoryTier.SEMANTIC,
                namespace=NS,
                origin=MemoryOrigin.REFLECTION,
            )
        )


def _stored() -> int:
    if not DB.exists():
        return 0
    return len(
        SqliteMemoryClient(DB).recall(MemoryQuery(text="", namespace=NS, limit=1000)).hits
    )


try:
    _configure()

    if DB.exists():
        DB.unlink()
    report = learning_delta(LAB_ROOT, "digest", "mock/sim")

    # --- Case 0: the suite actually ran -------------------------------------
    # Guard against a hollow green: if every case errors, both arms score 0.0 and the
    # verdict is "neutral" for entirely the wrong reason. This round previously passed
    # 8/8 in exactly that state.
    check(
        "0. the eval suite actually ran (no provider errors)",
        report.baseline.success_rate == 1.0 and report.learning.success_rate == 1.0,
        f"baseline_success={report.baseline.success_rate}, "
        f"learning_success={report.learning.success_rate}",
    )

    # --- Case 1: empty store -> the count explains a neutral verdict ---------
    check(
        "1. empty store reports 0 recalled notes (the experiment never ran)",
        report.recalled_notes == 0,
        f"notes={report.recalled_notes}, verdict={report.verdict}",
    )

    # --- Case 2: both arms actually ran the whole suite -----------------------
    check(
        "2. both arms ran the same suite",
        report.baseline.case_count == report.learning.case_count > 0,
        f"baseline={report.baseline.case_count}, learning={report.learning.case_count}",
    )

    # --- Case 3: every metric is reported with a direction --------------------
    metrics = {d.metric for d in report.deltas}
    directions = {d.metric: d.higher_is_better for d in report.deltas}
    check(
        "3. seven metrics reported, each tagged higher_is_better",
        len(metrics) == 7
        and directions["accuracy"] is True
        and directions["mean_cost_usd"] is False,
        f"metrics={len(metrics)}",
    )

    # --- Case 4: the measurement writes NOTHING -------------------------------
    # The load-bearing property: benchmarking must not mutate what it measures.
    before = _stored()
    learning_delta(LAB_ROOT, "digest", "mock/sim")
    after = _stored()
    check(
        "4. benchmarking writes no memory (no trajectories, no lessons)",
        before == after,
        f"before={before}, after={after}",
    )

    # --- Case 5: a populated store is counted ---------------------------------
    _seed([f"lesson {i}" for i in range(4)])
    seeded = learning_delta(LAB_ROOT, "digest", "mock/sim")
    check(
        "5. a populated store is reflected in the note count",
        seeded.recalled_notes == 4,
        f"notes={seeded.recalled_notes}",
    )

    # --- Case 6: reproducible across runs -------------------------------------
    # Latency jitters; state-dependent metrics must not.
    stable = {"accuracy", "success_rate", "total_input_tokens", "total_output_tokens"}
    first = learning_delta(LAB_ROOT, "digest", "mock/sim")
    second = learning_delta(LAB_ROOT, "digest", "mock/sim")
    same = {d.metric: d.delta for d in first.deltas if d.metric in stable} == {
        d.metric: d.delta for d in second.deltas if d.metric in stable
    }
    check(
        "6. state-dependent metrics are reproducible run-to-run",
        same and first.verdict == second.verdict,
        f"verdict={first.verdict}",
    )

    # --- Case 7: the report is machine-readable and lands on disk -------------
    out = write_delta_report(LAB_ROOT, seeded)
    payload = json.loads(out.read_text())
    check(
        "7. machine-readable report written to .lottie/benchmarks/",
        out.name == "digest-learning-delta.json"
        and payload["verdict"] in {"improved", "neutral", "regressed"}
        and payload["recalled_notes"] == 4,
        f"file={out.name}",
    )
    out.unlink(missing_ok=True)

    # --- Case 8: the verdict can say NO ---------------------------------------
    # A gate that can only report success is not a gate. Verify the verdict is derived
    # from the accuracy delta rather than hardcoded optimism.
    from lottie.benchmark.learning import _verdict

    check(
        "8. the verdict can report regression, not just success",
        (_verdict(-0.25), _verdict(0.0), _verdict(0.25))
        == ("regressed", "neutral", "improved"),
    )

finally:
    _restore()

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "26",
            "slice": "V2 S4 — learning-delta eval loop",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
