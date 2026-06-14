"""Round-7 governance driver — validate the SHIPPED audit trail + capability policy
engine against lottie-orchestrator @ feat/governance-policy-engine.

Runs the REAL shipped path in-process: `instantiate_agent` (which attaches the policy
gate) + the real `DigestAgent` + a scripted `MockLLMProvider` (offline, deterministic).
A blocked run leaves the MockLLM unconsumed (index 0) — proving `_execute` never ran.

For each case it writes inputs/case-NN.json (the scenario) and outputs/case-NN.out.txt
(the captured result), enabling the audit trail so each run's row can be read back. A
final case seeds a persistent project and renders `lottie audit`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from contextlib import chdir
from pathlib import Path

from lottie.governance.audit import SqliteAuditLogger
from lottie.governance.policy import (
    PolicyConfigError,
    PolicyDenied,
    PolicyEscalation,
)
from lottie.llm import MockLLMProvider
from lottie.project.config import AgentConfig
from lottie.project.discovery import instantiate_agent

from agents.digest.agent import DigestAgent
from agents.digest.schema import DigestAgentInput

HERE = Path(__file__).resolve().parent
INPUTS = HERE / "inputs"
OUTPUTS = HERE / "outputs"

_CAP = "text.summarize"

# Each case: id, desc, declared policies, capabilities, policy-file contents, expected
# outcome. A policy file value of {"_raw": "..."} writes the text verbatim (empty /
# malformed); otherwise allow/deny/escalate lists are rendered to YAML.
CASES: list[dict[str, object]] = [
    {
        "id": "01-no-policy",
        "desc": "No policy declared / no policy file present -> run succeeds (baseline).",
        "declared": [],
        "capabilities": [_CAP],
        "files": {},
        "expect": "ok",
    },
    {
        "id": "02-empty-policy",
        "desc": "Declared policy is a 0-byte file -> no rules -> run succeeds.",
        "declared": ["base"],
        "capabilities": [_CAP],
        "files": {"base": {"_raw": ""}},
        "expect": "ok",
    },
    {
        "id": "03-deny",
        "desc": "deny matches a declared capability -> PolicyDenied, blocked before _execute.",
        "declared": ["base"],
        "capabilities": [_CAP],
        "files": {"base": {"deny": [_CAP]}},
        "expect": "PolicyDenied",
    },
    {
        "id": "04-escalate",
        "desc": "escalate matches -> PolicyEscalation (distinct from deny), also blocks.",
        "declared": ["base"],
        "capabilities": [_CAP],
        "files": {"base": {"escalate": [_CAP]}},
        "expect": "PolicyEscalation",
    },
    {
        "id": "05-allow-whitelist",
        "desc": "Non-empty allow, capability NOT listed -> denied (default-deny whitelist).",
        "declared": ["base"],
        "capabilities": [_CAP],
        "files": {"base": {"allow": ["other.capability"]}},
        "expect": "PolicyDenied",
    },
    {
        "id": "06-deny-beats-allow",
        "desc": "deny + allow both match same capability -> deny wins (precedence).",
        "declared": ["base"],
        "capabilities": [_CAP],
        "files": {"base": {"deny": [_CAP], "allow": [_CAP]}},
        "expect": "PolicyDenied",
    },
    {
        "id": "07-union-two-files",
        "desc": "Two policy files union; the deny in the second file applies (order-independent).",
        "declared": ["base", "extra"],
        "capabilities": [_CAP],
        "files": {"base": {"deny": ["unrelated"]}, "extra": {"deny": [_CAP]}},
        "expect": "PolicyDenied",
        "also_reversed": True,
    },
    {
        "id": "08-malformed-yaml",
        "desc": "Malformed policy YAML -> fail-closed at instantiate (no silent allow).",
        "declared": ["base"],
        "capabilities": [_CAP],
        "files": {"base": {"_raw": "deny: [a, b\nallow: ::: not valid :::\n  - x\n"}},
        "expect": "PolicyConfigError",
    },
]


def _write_policy_files(root: Path, files: dict) -> None:
    if not files:
        return
    pol = root / "policies"
    pol.mkdir(parents=True, exist_ok=True)
    for name, rules in files.items():
        if "_raw" in rules:
            (pol / f"{name}.yaml").write_text(rules["_raw"], encoding="utf-8")
            continue
        lines = [f"name: {name}"]
        for key in ("allow", "deny", "escalate"):
            if rules.get(key):
                lines.append(f"{key}: [{', '.join(rules[key])}]")
        (pol / f"{name}.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _outcome(root: Path, declared: list, capabilities: list) -> tuple[str, int, str]:
    """Run digest via the real shipped path. Return (outcome, llm_calls, detail)."""
    cfg = AgentConfig.model_validate(
        {"provider": "mock/x", "capabilities": capabilities, "policies": declared}
    )
    llm = MockLLMProvider(["DIGEST: a concise summary of the input."])
    try:
        agent = instantiate_agent(DigestAgent, llm=llm, root=root, config=cfg)
    except PolicyConfigError as exc:
        return ("PolicyConfigError", 0, f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001 — capture the REAL type honestly
        return (type(exc).__name__, 0, f"{type(exc).__name__}: {exc}")
    try:
        out = agent.run(DigestAgentInput(query="Summarize multi-agent AI systems."))
    except PolicyDenied as exc:
        return ("PolicyDenied", llm._index, f"PolicyDenied: {exc}")
    except PolicyEscalation as exc:
        return ("PolicyEscalation", llm._index, f"PolicyEscalation: {exc}")
    except Exception as exc:  # noqa: BLE001
        return (type(exc).__name__, llm._index, f"{type(exc).__name__}: {exc}")
    return ("ok", llm._index, f"ok: {out.result[:60]}")


def _audit_status(root: Path) -> str:
    try:
        rows = SqliteAuditLogger(root).query(limit=1)
    except Exception:  # noqa: BLE001
        return "(no audit db)"
    return rows[0].status if rows else "(empty)"


def _run_case(case: dict) -> dict:
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (INPUTS / f"case-{case['id']}.json").write_text(
        json.dumps(case, indent=2) + "\n", encoding="utf-8"
    )

    os.environ.pop("LOTTIE_DISABLE_AUDIT", None)  # audit ON so we capture the row
    results = []
    orders = [case["declared"]]
    if case.get("also_reversed"):
        orders.append(list(reversed(case["declared"])))
    for declared in orders:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_policy_files(root, case["files"])
            with chdir(root):  # so the audit db lands under this tmp root
                outcome, calls, detail = _outcome(root, declared, case["capabilities"])
                status = _audit_status(root)
        results.append((declared, outcome, calls, status, detail))

    expect = case["expect"]
    blocked_outcomes = {"PolicyDenied", "PolicyEscalation", "PolicyConfigError"}
    ok_lines = []
    passed = True
    for declared, outcome, calls, status, detail in results:
        match = outcome == expect
        # A blocked run must NOT have invoked the LLM (proves _execute never ran).
        if outcome in blocked_outcomes and calls != 0:
            match = False
        passed = passed and match
        # Expected audit status for this outcome.
        want_status = {
            "ok": "ok",
            "PolicyDenied": "denied",
            "PolicyEscalation": "escalated",
        }.get(outcome)
        audit_ok = want_status is None or status == want_status
        passed = passed and audit_ok
        ok_lines.append(
            f"  order={declared} -> outcome={outcome} (expect {expect}) "
            f"llm_calls={calls} audit_status={status} | {detail}"
        )

    body = (
        f"CASE {case['id']}: {case['desc']}\n"
        f"declared_policies={case['declared']} capabilities={case['capabilities']}\n"
        + "\n".join(ok_lines)
        + f"\nRESULT: {'PASS' if passed else 'FAIL'}\n"
    )
    (OUTPUTS / f"case-{case['id']}.out.txt").write_text(body, encoding="utf-8")
    return {"id": case["id"], "passed": passed, "expect": expect, "lines": ok_lines}


def _audit_cli_demo() -> bool:
    """Case 09: seed a persistent project with denied + escalated + ok runs, then
    render `lottie audit` and confirm all three statuses appear."""
    demo = OUTPUTS / "audit-demo"
    demo.mkdir(parents=True, exist_ok=True)
    (demo / "lottie.yaml").write_text(
        "project: audit-demo\nproviders:\n  default: mock/x\n", encoding="utf-8"
    )
    # Clear any prior db so the demo is reproducible.
    db = demo / ".lottie" / "audit.db"
    if db.exists():
        db.unlink()
    os.environ.pop("LOTTIE_DISABLE_AUDIT", None)
    scenarios = [
        ([], {}),  # ok
        (["base"], {"base": {"deny": [_CAP]}}),  # denied
        (["base"], {"base": {"escalate": [_CAP]}}),  # escalated
    ]
    with chdir(demo):
        for declared, files in scenarios:
            _write_policy_files(demo, files)
            _outcome(demo, declared, [_CAP])
            for f in (demo / "policies").glob("*.yaml") if (demo / "policies").exists() else []:
                f.unlink()  # reset between scenarios
        rows = SqliteAuditLogger(demo).query(limit=10)
        statuses = {r.status for r in rows}
        lottie_bin = Path(sys.executable).parent / "lottie"
        cli = subprocess.run(
            [str(lottie_bin), "audit"],
            capture_output=True,
            text=True,
            cwd=demo,
        )
    out = cli.stdout + cli.stderr
    (OUTPUTS / "case-09-audit.out.txt").write_text(
        f"CASE 09-audit-integration: audit rows for denied/escalated/ok + `lottie audit` render.\n"
        f"audit statuses present: {sorted(statuses)}\n"
        f"lottie audit exit={cli.returncode}\n\n{out}\n",
        encoding="utf-8",
    )
    passed = {"ok", "denied", "escalated"} <= statuses and cli.returncode == 0
    return passed


def main() -> int:
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    summary = []
    for case in CASES:
        res = _run_case(case)
        summary.append(res)
        print(f"[{'PASS' if res['passed'] else 'FAIL'}] case {res['id']}")
        for line in res["lines"]:
            print(line)

    audit_pass = _audit_cli_demo()
    summary.append({"id": "09-audit-integration", "passed": audit_pass})
    print(f"[{'PASS' if audit_pass else 'FAIL'}] case 09-audit-integration")

    total = len(summary)
    passed = sum(1 for s in summary if s["passed"])
    print(f"\nRESULT: {passed}/{total} cases PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
