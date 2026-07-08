"""Round-18 HTTP hardening driver — validate orchestrator S4 (API-key auth, rate limiting,
pagination) from a downstream project.

Drives the real shipped app `build_http_app(LAB_ROOT)` (what `lottie serve --port` serves) via
Starlette's TestClient, toggling the env knobs per case. build_provider patched to a
MockLLMProvider; API keys unset except where a case sets them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from starlette.testclient import TestClient

import lottie.serve.service as service_mod
from lottie.llm import MockLLMProvider
from lottie.serve.http_app import build_http_app

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
LAB_ROOT = HERE.parent.parent

os.environ["LOTTIE_DISABLE_AUDIT"] = "1"
os.chdir(LAB_ROOT)
service_mod.build_provider = lambda _n: MockLLMProvider(["ok"])  # type: ignore[assignment]


def _client() -> TestClient:
    return TestClient(build_http_app(LAB_ROOT))


def _clear_env() -> None:
    os.environ.pop("LOTTIE_API_KEYS", None)
    os.environ.pop("LOTTIE_RATE_LIMIT_PER_MIN", None)


def _emit(name: str, detail: str, ok: bool) -> bool:
    (OUTPUTS / f"case-{name}.out.txt").write_text(
        f"{'PASS' if ok else 'FAIL'} — {name}\n\n{detail}\n", encoding="utf-8"
    )
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    return ok


def case_01_auth_open_when_unset() -> bool:
    _clear_env()
    ok = _client().get("/v1/agents").status_code == 200
    return _emit("01-auth-open", f"LOTTIE_API_KEYS unset -> open. status_ok={ok}", ok)


def case_02_auth_required_and_headers() -> bool:
    _clear_env()
    os.environ["LOTTIE_API_KEYS"] = "sk-alpha,sk-beta"
    try:
        c = _client()
        missing = c.get("/v1/agents")
        bearer = c.get("/v1/agents", headers={"Authorization": "Bearer sk-alpha"})
        xkey = c.get("/v1/agents", headers={"X-API-Key": "sk-beta"})
        wrong = c.get("/v1/agents", headers={"Authorization": "Bearer nope"})
        ok = (
            missing.status_code == 401
            and "sk-alpha" not in missing.text
            and bearer.status_code == 200
            and xkey.status_code == 200
            and wrong.status_code == 401
        )
        detail = (
            f"missing={missing.status_code} bearer={bearer.status_code} "
            f"xkey={xkey.status_code} wrong={wrong.status_code} no_key_echo="
            f"{'sk-alpha' not in missing.text}"
        )
    finally:
        _clear_env()
    return _emit("02-auth-required", detail, ok)


def case_03_rate_limit_then_429() -> bool:
    _clear_env()
    os.environ["LOTTIE_RATE_LIMIT_PER_MIN"] = "2"
    try:
        c = _client()
        s1 = c.get("/v1/agents").status_code
        s2 = c.get("/v1/agents").status_code
        s3 = c.get("/v1/agents").status_code  # bucket empty
        ok = s1 == 200 and s2 == 200 and s3 == 429
        detail = f"rate=2 -> {s1},{s2},{s3} (third is 429)"
    finally:
        _clear_env()
    return _emit("03-rate-limit", detail, ok)


def case_04_rate_limit_per_identity() -> bool:
    _clear_env()
    os.environ["LOTTIE_RATE_LIMIT_PER_MIN"] = "1"
    os.environ["LOTTIE_API_KEYS"] = "sk-a,sk-b"
    try:
        c = _client()
        ha = {"Authorization": "Bearer sk-a"}
        hb = {"Authorization": "Bearer sk-b"}
        a1 = c.get("/v1/agents", headers=ha).status_code
        a2 = c.get("/v1/agents", headers=ha).status_code  # a exhausted
        b1 = c.get("/v1/agents", headers=hb).status_code  # b independent
        ok = a1 == 200 and a2 == 429 and b1 == 200
        detail = f"per-key buckets: a={a1},{a2} b={b1}"
    finally:
        _clear_env()
    return _emit("04-rate-per-identity", detail, ok)


def case_05_pagination_agents() -> bool:
    _clear_env()
    c = _client()
    full = c.get("/v1/agents").json()["agents"]
    one = c.get("/v1/agents?limit=1").json()["agents"]
    page2 = c.get("/v1/agents?limit=1&offset=1").json()["agents"]
    empty = c.get("/v1/agents?offset=999").json()["agents"]
    ok = (
        len(full) >= 2
        and len(one) == 1
        and len(page2) == 1
        and page2[0]["name"] != one[0]["name"]
        and empty == []
    )
    return _emit(
        "05-pagination-agents",
        f"full={len(full)} limit1={len(one)} page2={len(page2)} past_end={len(empty)}",
        ok,
    )


def case_06_pagination_models() -> bool:
    _clear_env()
    c = _client()
    data = c.get("/v1/models").json()["data"]
    limited = c.get("/v1/models?limit=1").json()["data"]
    ok = len(limited) <= 1 and len(data) >= len(limited)
    return _emit(
        "06-pagination-models",
        f"/v1/models full={len(data)} limit1={len(limited)}",
        ok,
    )


def main() -> int:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    cases = [
        case_01_auth_open_when_unset,
        case_02_auth_required_and_headers,
        case_03_rate_limit_then_429,
        case_04_rate_limit_per_identity,
        case_05_pagination_agents,
        case_06_pagination_models,
    ]
    results = [c() for c in cases]
    passed, total = sum(results), len(results)
    print(f"\nRESULT: {passed}/{total} cases PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
