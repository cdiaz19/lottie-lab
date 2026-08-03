"""Round-28 runtime-kernel driver — validate orchestrator V3 S1 from downstream.

S1 ships a kernel with NO consumers, so there is no agent behaviour to observe. What a
downstream round can still prove is that the kernel behaves as advertised when a real
project drives it directly — and, critically, that its guarantees are structural rather
than conventional.

Cases 5-8 are adversarial: they are the ones a plugin author (V3 E7) could otherwise
exploit.
"""

from __future__ import annotations

import hashlib
import json
import sys
import warnings
from pathlib import Path

from pydantic import BaseModel

from lottie.runtime.context import ExecutionContext
from lottie.runtime.events import EventBus, RunBlocked, RunCompleted, RunEvent
from lottie.runtime.middleware import Next, Order
from lottie.runtime.pipeline import Pipeline, UnsafeHasherError
from lottie.runtime.registry import Deps, ModuleConflictError, ModuleRegistry, Mountable

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


class _In(BaseModel):
    text: str


class _Out(BaseModel):
    text: str


def _hasher(m: BaseModel) -> str:
    return hashlib.sha256(m.model_dump_json().encode()).hexdigest()


def _core(data: _In) -> _Out:
    return _Out(text=data.text.upper())


class _Gate:
    """A realistic fail-closed gate: reserves, then releases in a finally."""

    def __init__(self, label: str, order: int, log: list[str], *, deny: bool = False) -> None:
        self.name = label
        self.order = order
        self._log = log
        self._deny = deny

    def __call__(self, ctx: ExecutionContext, nxt: Next) -> BaseModel:
        if self._deny:
            raise PermissionError(f"{self.name} denied")
        self._log.append(f"reserve:{self.name}")
        ctx.scoped(self.name)["handle"] = "H1"
        try:
            return nxt(ctx)
        finally:
            assert ctx.scoped(self.name)["handle"] == "H1"
            self._log.append(f"settle:{self.name}")


class _Observer:
    def __init__(self, label: str, log: list[str]) -> None:
        self.name = label
        self._log = log

    def on_event(self, event: RunEvent) -> None:
        self._log.append(f"event:{type(event).__name__}")


# --- Case 1: a realistic chain runs in the right order ----------------------
log: list[str] = []
bus = EventBus()
bus.subscribe(_Observer("audit", log))
pipe: Pipeline[_In, _Out] = Pipeline(
    runnable="Demo",
    kind="agent",
    core=_core,
    hasher=_hasher,
    middleware=[_Gate("cost", Order.COST, log), _Gate("capability", Order.CAPABILITY, log)],
    bus=bus,
)
out = pipe.execute(_In(text="hi"))
check(
    "1. a realistic gate chain runs pre low-to-high, post high-to-low",
    log
    == [
        "reserve:cost",
        "reserve:capability",
        "event:RunStarted",
        "event:RunCompleted",
        "settle:capability",
        "settle:cost",
    ]
    and out.text == "HI",
    f"log={log}",
)

# --- Case 2: audit observes BEFORE cost settles -----------------------------
check(
    "2. RunCompleted reaches observers before the cost settle (audit-before-settle)",
    log.index("event:RunCompleted") < log.index("settle:cost"),
)

# --- Case 3: scoped state is isolated per module ----------------------------
seen: dict[str, object] = {}


class _Collide:
    def __init__(self, label: str, order: int) -> None:
        self.name = label
        self.order = order

    def __call__(self, ctx: ExecutionContext, nxt: Next) -> BaseModel:
        ctx.scoped(self.name)["token"] = self.name
        result = nxt(ctx)
        seen[self.name] = ctx.scoped(self.name)["token"]
        return result


Pipeline(
    runnable="Demo",
    kind="agent",
    core=_core,
    hasher=_hasher,
    middleware=[_Collide("a", 10), _Collide("b", 20)],
).execute(_In(text="x"))
check(
    "3. two modules using the same state key do not collide",
    seen == {"a": "a", "b": "b"},
    f"seen={seen}",
)

# --- Case 4: a denied run still releases its reservation --------------------
log2: list[str] = []
denied_ok = False
try:
    Pipeline(
        runnable="Demo",
        kind="agent",
        core=_core,
        hasher=_hasher,
        middleware=[
            _Gate("cost", Order.COST, log2),
            _Gate("policy", Order.POLICY + 15, log2, deny=True),
        ],
    ).execute(_In(text="x"))
except PermissionError:
    denied_ok = "settle:cost" in log2
check(
    "4. a denied run still releases the outer reservation",
    denied_ok,
    f"log={log2}",
)

# --- Case 5: a malicious subscriber cannot break a run ----------------------
class _Exploder:
    name = "malicious"

    def on_event(self, event: RunEvent) -> None:
        raise RuntimeError("plugin sabotage")


bus5 = EventBus()
bus5.subscribe(_Exploder())
survivor_log: list[str] = []
bus5.subscribe(_Observer("audit", survivor_log))
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    result5 = Pipeline(
        runnable="Demo", kind="agent", core=_core, hasher=_hasher, bus=bus5
    ).execute(_In(text="hi"))
check(
    "5. a sabotaging subscriber cannot fail a run, nor starve the next subscriber",
    result5.text == "HI" and survivor_log == ["event:RunStarted", "event:RunCompleted"],
    f"survivor={survivor_log}",
)

# --- Case 6: events carry NO raw content ------------------------------------
captured: list[RunEvent] = []


class _Sniffer:
    name = "sniffer"

    def on_event(self, event: RunEvent) -> None:
        captured.append(event)


bus6 = EventBus()
bus6.subscribe(_Sniffer())
Pipeline(runnable="Demo", kind="agent", core=_core, hasher=_hasher, bus=bus6).execute(
    _In(text="SENSITIVE_PAYLOAD")
)
leaked = any("SENSITIVE_PAYLOAD" in json.dumps(e.model_dump()) for e in captured)
check(
    "6. a subscriber cannot read raw input off the bus (hash-only contract)",
    not leaked and len(captured) == 2,
    f"events={len(captured)}, leaked={leaked}",
)

# --- Case 6b: an ECHOING hasher is refused, not silently trusted ------------
# The first version of this round injected `f"h:{model_dump_json()}"` as its hasher and
# watched the raw payload land on the bus. D6 is only as strong as the hasher, so the
# kernel now VERIFIES the digest shape instead of trusting the caller.
sniffed: list[RunEvent] = []


class _Sniffer2:
    name = "sniffer2"

    def on_event(self, event: RunEvent) -> None:
        sniffed.append(event)


bus6b = EventBus()
bus6b.subscribe(_Sniffer2())
refused = False
try:
    Pipeline(
        runnable="Demo",
        kind="agent",
        core=_core,
        hasher=lambda m: f"h:{m.model_dump_json()}",
        bus=bus6b,
    ).execute(_In(text="SENSITIVE_PAYLOAD"))
except UnsafeHasherError:
    refused = True
check(
    "6b. an echoing hasher is REFUSED and no event escapes with raw content",
    refused and sniffed == [],
    f"refused={refused}, events_emitted={len(sniffed)}",
)

# --- Case 7: events are frozen against tampering ----------------------------
tamper_blocked = False
try:
    captured[0].run_id = "hijacked"  # type: ignore[misc]
except Exception:
    tamper_blocked = True
check(
    "7. one subscriber cannot mutate what later subscribers observe",
    tamper_blocked,
)

# --- Case 8: a plugin cannot take an occupied chain slot --------------------
class _Config(BaseModel):
    on: bool = True


class _Security:
    name = "security"
    order = Order.SECURITY_INPUT

    def build(self, cfg: _Config, deps: Deps) -> Mountable | None:
        return None


class _Impostor:
    name = "impostor"
    order = Order.SECURITY_INPUT  # same slot as the security gate

    def build(self, cfg: _Config, deps: Deps) -> Mountable | None:
        return None


registry: ModuleRegistry[_Config] = ModuleRegistry()
registry.register(_Security())
conflict = ""
try:
    registry.register(_Impostor())
except ModuleConflictError as exc:
    conflict = str(exc)
check(
    "8. a plugin claiming an occupied order is rejected AT REGISTRATION",
    "impostor" in conflict and "security" in conflict,
    f"error={conflict!r}",
)

# --- Case 9: RunBlocked names the refusing gate -----------------------------
blocked: list[RunEvent] = []


class _BlockWatch:
    name = "watch"

    def on_event(self, event: RunEvent) -> None:
        if isinstance(event, RunBlocked):
            blocked.append(event)


bus9 = EventBus()
bus9.subscribe(_BlockWatch())
try:
    Pipeline(
        runnable="Demo",
        kind="agent",
        core=_core,
        hasher=_hasher,
        middleware=[_Gate("policy", Order.POLICY, [], deny=True)],
        bus=bus9,
    ).execute(_In(text="x"))
except PermissionError:
    pass
check(
    "9. a refused run emits RunBlocked naming the gate that refused",
    len(blocked) == 1 and getattr(blocked[0], "blocked_by", "") == "policy",
    f"blocked_by={getattr(blocked[0], 'blocked_by', None) if blocked else None}",
)

# --- Case 10: the kernel has no consumers yet -------------------------------
# S1's claim is zero behaviour change. Verify no shipped module imports it.
import subprocess

grep = subprocess.run(
    ["grep", "-rl", "lottie.runtime", str(Path(__import__("lottie").__file__).parent)],
    capture_output=True,
    text=True,
)
consumers = [
    line
    for line in grep.stdout.splitlines()
    if "/runtime/" not in line and line.endswith(".py")
]
check(
    "10. no shipped module consumes the kernel yet (zero behaviour change)",
    consumers == [],
    f"consumers={consumers}",
)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "28",
            "slice": "V3 S1 — runtime kernel",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
