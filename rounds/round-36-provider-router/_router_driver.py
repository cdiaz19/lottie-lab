"""Round-36 provider-router driver — validate orchestrator E5 S1 from downstream.

`lottie.yaml` has declared `providers.fallback` since Phase 0 and nothing read it. This
round's first job is to prove the config stopped lying.

Cases 4-6 are the ones that matter for safety. A fallback that retries ANYTHING would
launder a content-policy refusal and double the spend on deterministic failures — so what
the router REFUSES to do is as load-bearing as what it does.
"""

from __future__ import annotations

import json
import sys
import tempfile
from collections.abc import Generator, Mapping
from pathlib import Path

from lottie.llm.base import LLMProvider, LLMResponse, Message, StreamResult, TokenUsage
from lottie.llm.routing import RoutedProvider, is_transient
from lottie.project.discovery import resolve_provider

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


# Named after litellm's taxonomy; classified by NAME so nothing here imports litellm.
class RateLimitError(Exception): ...
class ContentPolicyViolationError(Exception): ...
class AuthenticationError(Exception): ...
class BrandNewProviderError(Exception): ...


class _Fake(LLMProvider):
    def __init__(self, name: str, *, raises: Exception | None = None) -> None:
        self._name = name
        self._raises = raises
        self.calls = 0

    @property
    def model(self) -> str:
        return self._name

    def complete(
        self, messages: list[Message], model_params: Mapping[str, object] | None = None
    ) -> LLMResponse:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return LLMResponse(content=f"from {self._name}", usage=TokenUsage(), model=self._name)

    def stream_complete(
        self, messages: list[Message], model_params: Mapping[str, object] | None = None
    ) -> Generator[str, None, StreamResult]:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        yield f"{self._name}-delta"
        return StreamResult(usage=TokenUsage(), cost_usd=0.0)


def _msgs() -> list[Message]:
    return [Message(role="user", content="hi")]


def _project(fallback: str | None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="round36-"))
    body = "project: r36\nproviders:\n  default: anthropic/primary\n"
    if fallback:
        body += f"  fallback: {fallback}\n"
    (root / "lottie.yaml").write_text(body)
    return root


# --- Case 1: the config stops lying -----------------------------------------
routed = resolve_provider(_project("openai/secondary"), "anthropic/primary")
check(
    "1. providers.fallback is finally honoured (config stops lying)",
    isinstance(routed, RoutedProvider)
    and routed.chain == ["anthropic/primary", "openai/secondary"],
    f"chain={getattr(routed, 'chain', None)}",
)

# --- Case 2: no fallback configured costs nothing ---------------------------
plain = resolve_provider(_project(None), "anthropic/primary")
check(
    "2. a project with no fallback is not wrapped at all",
    not isinstance(plain, RoutedProvider),
    f"type={type(plain).__name__}",
)

# --- Case 3: a transient failure advances -----------------------------------
primary, secondary = _Fake("a", raises=RateLimitError("429")), _Fake("b")
out = RoutedProvider([primary, secondary]).complete(_msgs())
check(
    "3. a transient failure advances to the fallback",
    out.content == "from b" and secondary.calls == 1,
    f"served={out.content!r}",
)

# --- Case 4: a content-policy refusal is NEVER shopped elsewhere ------------
# The one retry this framework must not make. Falling back here would launder a
# provider's safety decision through a framework that advertises fail-closed gates.
refused, untouched = _Fake("a", raises=ContentPolicyViolationError("refused")), _Fake("b")
laundered = True
try:
    RoutedProvider([refused, untouched]).complete(_msgs())
except ContentPolicyViolationError:
    laundered = False
check(
    "4. a content-policy refusal is NEVER retried on the fallback",
    not laundered and untouched.calls == 0,
    f"secondary_calls={untouched.calls}",
)

# --- Case 5: deterministic failures fail fast -------------------------------
# An auth error fails identically on the fallback, so retrying only doubles the spend.
bad_key, spared = _Fake("a", raises=AuthenticationError("401")), _Fake("b")
failed_fast = False
try:
    RoutedProvider([bad_key, spared]).complete(_msgs())
except AuthenticationError:
    failed_fast = True
check(
    "5. an auth error fails fast rather than doubling the spend",
    failed_fast and spared.calls == 0,
    f"secondary_calls={spared.calls}",
)

# --- Case 6: an unknown exception does not widen the surface ---------------
check(
    "6. an unrecognised provider error defaults to NOT transient",
    is_transient(BrandNewProviderError()) is False,
    "new SDK error types cannot silently widen the fallback",
)

# --- Case 7: the audit sees who actually served ----------------------------
# `agent.provider` feeds the audit record, so it must name what RAN.
routed = RoutedProvider([_Fake("a", raises=RateLimitError()), _Fake("b")])
routed.complete(_msgs())
check(
    "7. model reports the provider that actually served, for the audit record",
    routed.model == "b",
    f"model={routed.model}",
)

# --- Case 8: a fallback is never silent -------------------------------------
seen: list[tuple[str, str]] = []
RoutedProvider(
    [_Fake("a", raises=RateLimitError()), _Fake("b")],
    on_fallback=lambda frm, to, exc: seen.append((frm, to)),
).complete(_msgs())
check(
    "8. a fallback notifies — it is never silent",
    seen == [("a", "b")],
    f"notified={seen}",
)

# --- Case 9: streaming falls back only BEFORE the first delta --------------
class _PartialThenFails(LLMProvider):
    @property
    def model(self) -> str:
        return "a"

    def complete(
        self, messages: list[Message], model_params: Mapping[str, object] | None = None
    ) -> LLMResponse:
        raise NotImplementedError

    def stream_complete(
        self, messages: list[Message], model_params: Mapping[str, object] | None = None
    ) -> Generator[str, None, StreamResult]:
        yield "partial"
        raise RateLimitError("died mid-stream")


spliced = _Fake("b")
seen_deltas: list[str] = []
mid_stream_ok = False
try:
    for piece in RoutedProvider([_PartialThenFails(), spliced]).stream_complete(_msgs()):
        seen_deltas.append(piece)
except RateLimitError:
    mid_stream_ok = True
check(
    "9. a mid-stream failure never falls back (no spliced answer from two models)",
    mid_stream_ok and seen_deltas == ["partial"] and spliced.calls == 0,
    f"deltas={seen_deltas}, secondary_calls={spliced.calls}",
)

# --- Case 10: streaming DOES fall back before any delta --------------------
recovered = list(
    RoutedProvider([_Fake("a", raises=RateLimitError()), _Fake("b")]).stream_complete(_msgs())
)
check(
    "10. a transient failure before the first delta does fall back",
    recovered == ["b-delta"],
    f"deltas={recovered}",
)

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
OUTPUTS.mkdir(parents=True, exist_ok=True)
(OUTPUTS / "results.json").write_text(
    json.dumps(
        {
            "round": "36",
            "slice": "E5 S1 — provider router",
            "passed": passed,
            "total": total,
            "cases": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
        },
        indent=2,
    )
)
print(f"\nRESULT {'PASS' if passed == total else 'FAIL'} — {passed}/{total}")
sys.exit(0 if passed == total else 1)
