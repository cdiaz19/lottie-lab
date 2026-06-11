"""Round-5 MCP in-memory client driver.

MCP is a stdio server, not an argv CLI, so (unlike Round 4's `lottie <argv>`
runner) each input case is driven through the MCP SDK's in-memory client
against a live `build_mcp_server(LAB_ROOT)`. The LLM provider is mocked
(`MockLLMProvider`) so no API key is needed and outputs are deterministic —
the same seam the orchestrator's own MCP unit tests use.

Reads one inputs/input-*.json, runs its op, prints a JSON result to stdout.
Exit 0 if all declared `_expect_*` checks pass, else 1 (with MISS lines on
stderr).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from mcp.shared.memory import create_connected_server_and_client_session

from lottie.llm import MockLLMProvider
from lottie.serve.mcp_server import build_mcp_server

LAB_ROOT = Path(os.environ["LAB_ROOT"])


async def _run(case: dict[str, Any]) -> dict[str, Any]:
    mock_resp = str(case.get("mock_response", "mock"))
    with patch(
        "lottie.serve.service.build_provider",
        lambda name: MockLLMProvider([mock_resp]),
    ):
        server = build_mcp_server(LAB_ROOT)
        async with create_connected_server_and_client_session(server) as client:
            if case["op"] == "list_tools":
                res = await client.list_tools()
                return {
                    "tools": [
                        {
                            "name": t.name,
                            "schema_props": sorted(
                                (t.inputSchema or {}).get("properties", {}).keys()
                            ),
                        }
                        for t in res.tools
                    ]
                }
            if case["op"] == "call_tool":
                res = await client.call_tool(case["tool"], case.get("arguments", {}))
                return {
                    "isError": bool(res.isError),
                    "structuredContent": res.structuredContent,
                    "content_texts": [
                        c.text for c in res.content if getattr(c, "type", None) == "text"
                    ],
                }
            raise ValueError(f"unknown op: {case['op']}")


def _check(case: dict[str, Any], result: dict[str, Any]) -> int:
    miss = 0
    if "_expect_tools" in case:
        got = {t["name"] for t in result.get("tools", [])}
        for name in case["_expect_tools"]:
            if name not in got:
                print(f"  MISS tool: {name}", file=sys.stderr)
                miss = 1
        prop = case.get("_expect_schema_prop")
        if prop:
            for t in result.get("tools", []):
                if prop not in t["schema_props"]:
                    print(f"  MISS schema prop {prop} on {t['name']}", file=sys.stderr)
                    miss = 1
    if case.get("_expect_not_error") and result.get("isError"):
        print("  MISS: expected success, got isError", file=sys.stderr)
        miss = 1
    if case.get("_expect_error") and not result.get("isError"):
        print("  MISS: expected isError, got success", file=sys.stderr)
        miss = 1
    for key in case.get("_expect_structured_keys", []):
        if key not in (result.get("structuredContent") or {}):
            print(f"  MISS structured key: {key}", file=sys.stderr)
            miss = 1
    for sub in case.get("_expect_content_contains", []):
        if not any(sub in t for t in result.get("content_texts", [])):
            print(f"  MISS content substring: {sub}", file=sys.stderr)
            miss = 1
    return miss


def main() -> int:
    case = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    result = asyncio.run(_run(case))
    print(json.dumps(result, indent=2, default=str))
    return _check(case, result)


if __name__ == "__main__":
    sys.exit(main())
