"""Round-38 plugin-SDK driver — validate orchestrator E7 from downstream.

E7 freezes a PUBLIC extension API, so this round is written from the position of someone
who might abuse it. A plugin runs in-process with the host's privileges and is not
sandboxed — the only real lever is how much of the system it is handed, and every case
here probes that boundary.
"""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
import warnings
from pathlib import Path

from pydantic import BaseModel

from lottie.core.base_agent import BaseAgent
from lottie.core.middleware import build_chain
from lottie.governance.audit import SqliteAuditLogger
from lottie.llm import MockLLMProvider
from lottie.plugins import PluginLoadError, RunCompleted, RunEvent, load_plugin

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
_SCRATCH = Path(tempfile.mkdtemp(prefix="round38-"))

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


class _In(BaseModel):
    task: str


class _Out(BaseModel):
    answer: str


class _Agent(BaseAgent[_In, _Out]):
    def _execute(self, data: _In) -> _Out:
        return _Out(answer=data.task.upper())


class Telemetry:
    """A well-behaved plugin — the case the API is for."""

    name = "telemetry"

    def __init__(self) -> None:
        self.seen: list[RunEvent] = []

    def on_event(self, event: RunEvent) -> None:
        self.seen.append(event)


class Sabotage:
    name = "sabotage"

    def on_event(self, event: RunEvent) -> None:
        raise RuntimeError("plugin sabotage")


class WantsToIntercept:
    """Shaped like middleware — the thing the API deliberately refuses."""

    name = "interceptor"
    order = 50

    def __call__(self, ctx: object, nxt: object) -> object:
        raise NotImplementedError


class NotEvenClose:
    name = "impostor"


def _agent(*plugins: object) -> _Agent:
    agent = _Agent(llm=MockLLMProvider(responses=["ok"] * 4), enable_benchmarks=False)
    agent.set_plugins(list(plugins))  # type: ignore[arg-type]
    return agent


try:
    # --- Case 1: the happy path -------------------------------------------
    tel = Telemetry()
    out = _agent(tel).run(_In(task="hello"))
    check(
        "1. a well-behaved plugin receives real run events",
        out.answer == "HELLO" and [type(e).__name__ for e in tel.seen]
        == ["RunStarted", "RunCompleted"],
        f"events={[type(e).__name__ for e in tel.seen]}",
    )

    # --- Case 2: a plugin CANNOT read the task ----------------------------
    tel = Telemetry()
    _agent(tel).run(_In(task="SENSITIVE_TASK_TEXT"))
    leaked = any("SENSITIVE_TASK_TEXT" in e.model_dump_json() for e in tel.seen)
    check(
        "2. a plugin cannot read the task — events are hash-only",
        not leaked,
        f"events={len(tel.seen)}, leaked={leaked}",
    )

    # --- Case 3: a plugin CANNOT read the output --------------------------
    tel = Telemetry()
    _agent(tel).run(_In(task="secret"))
    completed = [e for e in tel.seen if isinstance(e, RunCompleted)]
    check(
        "3. a plugin cannot read the output either",
        completed and "SECRET" not in completed[0].model_dump_json(),
        "output_sha256 only",
    )

    # --- Case 4: a middleware-shaped plugin is REFUSED --------------------
    _HERE = "__main__"
    refused = False
    reason = ""
    try:
        load_plugin(f"{_HERE}:WantsToIntercept")
    except PluginLoadError as exc:
        refused, reason = True, str(exc)
    check(
        "4. a middleware-shaped plugin is refused at load",
        refused and "abort a run" in reason,
        "and the error explains why",
    )

    # --- Case 5: the guarantee is the MOUNTING, not the isinstance --------
    # runtime_checkable only checks method presence, so the real bound is that a plugin
    # only ever reaches bus.subscribe and never enters the chain.
    agent = _agent(Telemetry())
    chain_names = {m.name for m in build_chain(agent)}
    check(
        "5. a plugin never enters the middleware chain",
        "telemetry" not in chain_names,
        f"chain={sorted(chain_names)}",
    )

    # --- Case 6: a sabotaging plugin cannot fail a run --------------------
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        survived = _agent(Sabotage()).run(_In(task="hi"))
    check(
        "6. a plugin that raises on every event cannot fail the run",
        survived.answer == "HI",
        f"result={survived.answer!r}",
    )

    # --- Case 7: it cannot starve the next plugin -------------------------
    survivor = Telemetry()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _agent(Sabotage(), survivor).run(_In(task="hi"))
    check(
        "7. a sabotaging plugin cannot starve the next one",
        len(survivor.seen) == 2,
        f"survivor_events={len(survivor.seen)}",
    )

    # --- Case 8: it cannot displace the audit record ----------------------
    ledger = _SCRATCH / "audit.db"
    agent = _agent(Sabotage())
    agent._audit = SqliteAuditLogger(ledger)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        agent.run(_In(task="hi"))
    check(
        "8. a sabotaging plugin cannot displace the audit record",
        len(SqliteAuditLogger(ledger).query()) == 1,
        "plugins subscribe after audit, and the bus isolates each dispatch",
    )

    # --- Case 9: a non-subscriber is refused ------------------------------
    bad = False
    try:
        load_plugin(f"{_HERE}:NotEvenClose")
    except PluginLoadError:
        bad = True
    check("9. a non-subscriber is refused at load, by shape", bad)

    # --- Case 10: there is NO auto-discovery ------------------------------
    # Nothing loads that the config did not name. A plugin class sitting in an imported
    # module is inert until something names it.
    unnamed = _agent()  # no plugins configured
    check(
        "10. nothing loads that the config did not name",
        unnamed._plugins == [] and unnamed.run(_In(task="hi")).answer == "HI",
        "no discovery step exists",
    )

    # --- Case 11: a bad path fails loudly, never silently -----------------
    fatal = False
    try:
        load_plugin("no.such.package:Thing")
    except PluginLoadError:
        fatal = True
    check(
        "11. an unimportable plugin fails loudly rather than being skipped",
        fatal,
        "a silently-skipped exporter would look like it was running",
    )

    # --- Case 12: there is ONE extension path, and it is subscribers -------
    # S1 shipped a `ModuleRegistry` for third-party module factories that the runtime
    # never adopted — S6 mounted agent-coupled adapters instead, because every real
    # module needs the agent, not the `Deps(bus, root)` the registry offered. Leaving it
    # in place advertised a mounting path that did nothing: an author would register a
    # factory and silently get no module. It was deleted; this pins that it stays gone.
    registry_gone = False
    try:
        importlib.import_module("lottie.runtime.registry")
    except ModuleNotFoundError:
        registry_gone = True
    check(
        "12. no second, dead mounting path — a plugin is a subscriber or nothing",
        registry_gone,
        "a factory registry that mounts nothing is worse than no API at all",
    )

    # --- Case 13: the order-conflict guard survived the deletion -----------
    # It is the one rule the registry held that mattered: a plugin must never be able to
    # take a security gate's slot. It moved to the code that composes the real chain.
    from lottie.core.middleware import build_chain
    from lottie.runtime.middleware import ModuleConflictError, Order

    class _Squatter:
        name = "squatter"
        order = Order.SECURITY_INPUT

        def __call__(self, ctx, nxt):  # pragma: no cover
            raise AssertionError("a conflicting chain must never be built")

    squat_agent = _agent()
    squat_agent._recall_module = lambda: _Squatter()
    refused = False
    try:
        build_chain(squat_agent)
    except ModuleConflictError:
        refused = True
    check(
        "13. a module claiming the input gate's slot is refused at composition",
        refused,
        "displacing a security gate must fail at startup, not at run time",
    )

finally:
    import shutil

    shutil.rmtree(_SCRATCH, ignore_errors=True)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "38",
            "slice": "E7 — plugin SDK",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
