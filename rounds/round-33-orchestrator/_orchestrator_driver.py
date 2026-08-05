"""Round-33 orchestrator driver — validate orchestrator V3 S6 from downstream.

S6 made the runtime chain visible and configurable. The operator-facing question this
answers is "what is actually wrapping my agent's runs?" — previously answerable only by
reading source.

Cases 5-8 are the ones that matter for safety: a typo must not silently do nothing, a
disabled security gate must be reported loudly, and two modules must never quietly share
a slot.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from lottie.core.middleware import KNOWN_MODULES, build_chain
from lottie.llm import MockLLMProvider
from lottie.project.config import AgentConfig
from lottie.project.discovery import instantiate_agent
from lottie.runtime.registry import ModuleConflictError

from agents.digest.agent import DigestAgent
from agents.digest.schema import DigestAgentInput

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def _agent(**cfg: object) -> DigestAgent:
    return instantiate_agent(  # type: ignore[return-value]
        DigestAgent,
        llm=MockLLMProvider(["an answer"] * 3),
        root=LAB_ROOT,
        config=AgentConfig.model_validate({"provider": "mock/sim", **cfg}),
        enable_benchmarks=False,
    )


# --- Case 1: the chain is visible -------------------------------------------
mounted = _agent().mounted_modules()
check(
    "1. the mounted chain is reportable, in execution order",
    len(mounted) == 11 and mounted[0] == "security_input" and mounted[-1] == "capability",
    f"mounted={len(mounted)}",
)

# --- Case 2: order matches the declared table -------------------------------
orders = [m.order for m in sorted(build_chain(_agent()), key=lambda m: m.order)]
check(
    "2. the chain is ordered and every position is distinct",
    orders == sorted(orders) and len(set(orders)) == len(orders),
    f"orders={orders}",
)

# --- Case 3: a module can be switched off -----------------------------------
off = _agent(modules={"recall": {"enabled": False}})
check(
    "3. a module can be disabled per agent",
    "recall" not in off.mounted_modules() and len(off.mounted_modules()) == 10,
    f"mounted={len(off.mounted_modules())}",
)

# --- Case 4: a disabled module is never CONSTRUCTED -------------------------
# Not merely skipped at run time — it costs nothing at all.
check(
    "4. a disabled module is never constructed",
    "recall" not in {m.name for m in build_chain(off, off._disabled_modules)},
)

# --- Case 5: the agent still runs with a module removed ---------------------
check(
    "5. an agent with a disabled module still runs",
    off.run(DigestAgentInput(query="q")).result == "an answer",
)

# --- Case 6: an unknown module name is detectable ---------------------------
# A typo here does NOTHING, which is the dangerous kind of nothing: the operator
# believes a gate is off when it is still mounted.
typo = _agent(modules={"recal": {"enabled": False}})
unknown = set(typo._disabled_modules) - set(KNOWN_MODULES)
check(
    "6. a typo'd module name is detectable rather than silently inert",
    unknown == {"recal"} and len(typo.mounted_modules()) == 11,
    f"unknown={unknown}, still_mounted={len(typo.mounted_modules())}",
)

# --- Case 7: disabling a security gate is visible ---------------------------
ungated = _agent(modules={"security_input": {"enabled": False}})
check(
    "7. disabling a fail-closed gate is visible in the mounted chain",
    "security_input" not in ungated.mounted_modules(),
    f"mounted={len(ungated.mounted_modules())}",
)

# --- Case 8: two modules cannot share a slot --------------------------------
agent = _agent()
chain = build_chain(agent)
clash = type(chain[0])
original = clash.order
conflict = ""
try:
    clash.order = chain[1].order
    try:
        build_chain(agent)
    except ModuleConflictError as exc:
        conflict = str(exc)
finally:
    clash.order = original
check(
    "8. two modules claiming one slot is rejected at composition",
    "already held by" in conflict,
    f"error={conflict!r}",
)

# --- Case 9: KNOWN_MODULES tracks the real chain ---------------------------
check(
    "9. KNOWN_MODULES matches the real chain (doctor cannot drift)",
    set(KNOWN_MODULES) == {m.name for m in build_chain(_agent())},
)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "33",
            "slice": "V3 S6 — module orchestrator",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
