"""Round-21 — full V1 regression smoke. Re-runs every v1 slice's round driver (R15–R20)
against the merged orchestrator `main` (v1.0.0) and aggregates the result. One green run here
is the downstream sign-off that the whole V1 surface still works end-to-end together.

Each round driver is a standalone `main() -> int` (0 = all cases pass). We import and invoke
them in a clean cwd so their env toggles don't leak across rounds.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parent.parent

# (round dir, driver filename) in slice order S1..S6.
_ROUNDS = [
    ("round-15-capability", "_capability_driver.py"),
    ("round-16-security-gate", "_security_gate_driver.py"),
    ("round-17-cost-caps", "_cost_caps_driver.py"),
    ("round-18-http-hardening", "_http_hardening_driver.py"),
    ("round-19-hitl-edited-input", "_hitl_edited_input_driver.py"),
    ("round-20-agentic-hygiene", "_agentic_hygiene_driver.py"),
]

# Env each driver expects to own; reset between rounds so toggles don't leak.
_ENV_KEYS = [
    "LOTTIE_API_KEYS", "LOTTIE_RATE_LIMIT_PER_MIN", "LOTTIE_DISABLE_AUDIT",
    "LOTTIE_MESH_CHECKPOINT",
]


def _reset_env() -> None:
    for k in _ENV_KEYS:
        os.environ.pop(k, None)


def _run_driver(round_dir: str, filename: str) -> int:
    path = LAB_ROOT / "rounds" / round_dir / filename
    spec = importlib.util.spec_from_file_location(f"_r21_{round_dir}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    os.chdir(LAB_ROOT)
    _reset_env()
    spec.loader.exec_module(module)
    return int(module.main())


def main() -> int:
    print("=== Round 21 — V1 full regression (orchestrator v1.0.0) ===\n")
    results: list[tuple[str, bool]] = []
    for round_dir, filename in _ROUNDS:
        print(f"--- {round_dir} ---")
        rc = _run_driver(round_dir, filename)
        results.append((round_dir, rc == 0))
        print()
    print("=== SUMMARY ===")
    for name, ok in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\nRESULT: {passed}/{total} v1 rounds PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
