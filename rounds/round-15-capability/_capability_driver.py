"""Round-15 capability-enforcement driver — validate orchestrator rule 11 (per-skill-call
capability enforcement, S1 of the v1 hardening epic) from a downstream project.

Drives the REAL shipped path in-process:
  * `instantiate_agent(CuratorAgent, config=...)` — the canonical CLI/serve dispatch that
    attaches the capability gate from `config.capabilities`. CuratorAgent calls
    `SummarizerSkill` (capability name "summarizer") inside `_execute`, so the call is
    allowed or blocked purely by what the config declares.
  * `build_http_app(LAB_ROOT)` via Starlette TestClient — the same app `lottie serve --port`
    serves — to prove the framework's OWN security skills (InputSanitizer/SecretDetection,
    invoked by the SecurityGate OUTSIDE `_execute`) are EXEMPT even under a narrow whitelist.

`build_provider` is patched to a MockLLMProvider (no real LLM; API keys unset).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from starlette.testclient import TestClient

import lottie.serve.service as service_mod
from lottie.governance.capability import CapabilityDenied
from lottie.llm import MockLLMProvider
from lottie.project.config import AgentConfig
from lottie.project.discovery import instantiate_agent
from lottie.serve.http_app import build_http_app

from agents.curator.agent import CuratorAgent
from agents.curator.schema import CuratorAgentInput
from skills.summarizer.skill import SummarizerSkill

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent  # lottie-lab project root (lottie.yaml + agents/ + policies/)

os.environ["LOTTIE_DISABLE_AUDIT"] = "1"
os.chdir(LAB_ROOT)


def _provider(_name: str) -> MockLLMProvider:
    return MockLLMProvider(["unused — curator does no LLM call"])


service_mod.build_provider = _provider  # type: ignore[assignment]


def _config(capabilities: list[str]) -> AgentConfig:
    return AgentConfig.model_validate(
        {
            "provider": "mock/curator",
            "capabilities": capabilities,
            "policies": ["base"],
        }
    )


def _curator(capabilities: list[str]) -> CuratorAgent:
    agent = instantiate_agent(
        CuratorAgent,
        llm=MockLLMProvider(["x"]),
        root=LAB_ROOT,
        config=_config(capabilities),
        enable_benchmarks=False,
    )
    return agent  # type: ignore[return-value]


def _emit(name: str, detail: str, ok: bool) -> bool:
    (OUTPUTS / f"case-{name}.out.txt").write_text(
        f"{'PASS' if ok else 'FAIL'} — {name}\n\n{detail}\n", encoding="utf-8"
    )
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def case_01_declared_skill_allowed() -> bool:
    agent = _curator(["summarizer"])
    out = agent.run(CuratorAgentInput(text="hello world"))
    ok = out.result == "hello world"
    return _emit(
        "01-declared-allowed",
        "capabilities=[summarizer]; CuratorAgent calls SummarizerSkill -> allowed.\n"
        f"result={out.result!r}",
        ok,
    )


def case_02_undeclared_skill_blocked() -> bool:
    agent = _curator(["something-else"])  # summarizer NOT declared
    blocked = False
    msg = ""
    try:
        agent.run(CuratorAgentInput(text="hello"))
    except CapabilityDenied as exc:
        blocked = True
        msg = str(exc)
    ok = blocked and "summarizer" in msg
    return _emit(
        "02-undeclared-blocked",
        "capabilities=[something-else]; the SummarizerSkill call is blocked fail-closed "
        "BEFORE the skill runs.\n"
        f"raised=CapabilityDenied={blocked} msg={msg!r}",
        ok,
    )


def case_03_empty_capabilities_no_enforcement() -> bool:
    agent = _curator([])  # whitelist-when-nonempty: empty -> no enforcement
    out = agent.run(CuratorAgentInput(text="ok"))
    ok = out.result == "ok"
    return _emit(
        "03-empty-no-enforcement",
        "capabilities=[]; NullCapabilityGate -> the skill call is unenforced (back-compat).\n"
        f"result={out.result!r}",
        ok,
    )


def case_04_capability_name_derivation() -> bool:
    derived = SummarizerSkill.resolved_capability_name()
    ok = derived == "summarizer"
    return _emit(
        "04-name-derivation",
        "Skill identity = class name minus 'Skill', lowercased -> matches config vocab.\n"
        f"SummarizerSkill.resolved_capability_name()={derived!r}",
        ok,
    )


def case_05_framework_skills_exempt_over_http() -> bool:
    """A REST run of curator (declares only [summarizer]) goes through the SecurityGate,
    which invokes InputSanitizer/SecretDetection skills OUTSIDE `_execute`. Those framework
    skills are NOT declared by curator, yet the run must succeed -> they are exempt."""
    client = TestClient(build_http_app(LAB_ROOT))
    resp = client.post("/v1/agents/curator/run", json={"text": "digest this"})
    body = resp.json()
    ok = (
        resp.status_code == 200
        and body.get("status") == "complete"
        and body.get("output", {}).get("result") == "digest this"
    )
    return _emit(
        "05-framework-exempt-http",
        "POST /v1/agents/curator/run (config caps=[summarizer]) through the real serve gate.\n"
        "SecurityGate's InputSanitizer/SecretDetection skills run outside _execute -> exempt;\n"
        "curator's own SummarizerSkill call is allowed. No spurious CapabilityDenied.\n"
        f"status={resp.status_code} body_status={body.get('status')} "
        f"result={body.get('output', {}).get('result')!r}",
        ok,
    )


def main() -> int:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    cases = [
        case_01_declared_skill_allowed,
        case_02_undeclared_skill_blocked,
        case_03_empty_capabilities_no_enforcement,
        case_04_capability_name_derivation,
        case_05_framework_skills_exempt_over_http,
    ]
    results = [c() for c in cases]
    passed, total = sum(results), len(results)
    print(f"\nRESULT: {passed}/{total} cases PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
