# Round 5 — MCP stdio Transport (Phase 4 slice 1)
> First transport on the serving core · `lottie serve` MCP stdio server · one typed tool per agent · `build_mcp_server` / `serve_stdio` · `call_tool` → output + metrics · `ServeError` → `isError`

## Goal
Verify the **first Phase-4 transport** of `lottie-orchestrator` — an **MCP stdio server** that
exposes each discovered agent as a typed MCP tool — end-to-end on **Mock providers (API keys
unset)**, and sign off the Round-5 checklist (§7 in `results.md`) so `feat/mcp-stdio` (PR #6) can
merge to `main`. The transport is a pure wrapper over the Round-3 `AgentService`: no core changes.
The slice is done when an MCP host can list one tool per healthy agent (schema from each agent's
`Input` model), call a tool and receive the agent output as `structuredContent` plus a metrics text
line, every `ServeError` surfaces as an MCP `isError` result, the `lottie serve` CLI runs the stdio
loop (with a friendly install hint when the optional `[serve]` extra is absent), and the full gate
(`pytest -q`, `mypy --strict src`, `ruff`) is green with the optional `mcp` dep kept out of the base
import path.

## What's being tested
1. **MCP tool registration** (group A) — `build_mcp_server(root)` discovers agents, registers one
   `types.Tool` per healthy agent with `inputSchema = Input.model_json_schema()`; a broken agent is
   logged and skipped (never fatal).
2. **`call_tool` run + return + error mapping** (A) — threadpool-wraps the sync `run_agent`; returns
   `(metrics_text, output)` → `structuredContent` + a `[lottie] …ms · …tok · $…` line; every
   `ServeError` (`InvalidInputError` / `AgentExecutionError` / `AgentNotFoundError` / `AgentLoadError`)
   → `isError`. `validate_input=False` keeps `run_agent`'s Pydantic the sole validator.
3. **`serve_stdio` run loop** (A) — `_run_stdio_blocking` seam so `serve_stdio(root)` is testable
   without blocking on real stdin.
4. **`lottie serve` CLI** (group B) — lazy-imports the transport; missing `[serve]` extra →
   friendly `pip install lottie-orchestrator[serve]` `BadParameter`; otherwise
   `serve_stdio(find_project_root())`.
5. **Optional-dep hygiene** (A/B) — `import lottie.serve` works WITHOUT `mcp`; `mcp` is imported only
   inside `serve/mcp_server.py`, reached lazily via the CLI. Base install stays lean.
6. **Serve-core regression** (group C) — the Round-3 `AgentService` + identity `SecurityGate`
   contract still holds under the new transport (`pytest src/lottie/serve`).
7. **Full gate** — `pytest -q` (full suite), `mypy --strict src`, `ruff`, serve-package coverage.

## Build / verify sequence

```bash
# From lottie-orchestrator (installed -e into the lab venv), API keys UNSET.
# Code under test: feat/mcp-stdio @ c951030. Outputs tee'd into
# ../lottie-lab/rounds/round-5-mcp-transport/outputs/.
pytest src/lottie/serve/tests/test_mcp_server.py -v   # A — MCP server (list_tools/call_tool/serve_stdio)
pytest src/lottie/cli/tests/test_serve.py -v          # B — lottie serve CLI (install hint + wiring)
pytest src/lottie/serve -v                            # C — serve-core regression (gate + errors)
pytest -q                                             # full-suite
pytest -q --cov=lottie --cov-report=term-missing      # coverage
mypy --strict src                                     # mypy  (requires the [serve] extra installed)
ruff check .                                          # ruff
```

Then run the input cases (MCP in-memory client, not argv CLI):

```bash
bash rounds/round-5-mcp-transport/run-inputs.sh   # 5 cases → outputs/input-*.out.json
```

## Inputs
See `inputs/`. MCP is a stdio server, not an argv CLI, so — unlike Round 4's `lottie <argv>` runner —
each `input-*.json` declares an `op` (`list_tools` | `call_tool`) driven through the MCP SDK's
**in-memory client** (`create_connected_server_and_client_session`) against a live
`build_mcp_server(LAB_ROOT)` by `_mcp_driver.py`. The provider is mocked (`MockLLMProvider`) — the
same seam the orchestrator's own MCP unit tests use — so no API key is needed and outputs are
deterministic. Cases: list-tools (digest + reviewer), call-digest (happy), call-reviewer (happy,
proves per-agent routing), bad-payload (→ `isError`), unknown-tool (→ `isError`). Each carries
`_expect_*` checks; raw results land in `outputs/`, signed-off summary in `results.md`.

## Definition of done
Every box in `results.md` §7 checked, full suite green, `mypy --strict` + `ruff` clean, the optional
`mcp` dep kept out of the base import (`import lottie.serve` works without it), one typed tool per
agent listed with the right schema, `call_tool` returns output as `structuredContent` + a metrics
line, every `ServeError` mapped to `isError`. Round 5 done → merge `feat/mcp-stdio` to `main`, open
Round 6 (next Phase-4 slice: REST + OpenAI-compat → shared ASGI app → `lottie serve --port`).

## Deviations from plan
- **Mock provider for `call_tool` happy paths.** Round 3 ran `digest` **live** (real API call). Round 5
  mocks `build_provider` (keys unset), matching Round 4's ethos and the orchestrator's own MCP unit
  tests. Consequence: the metrics line reads `[lottie] 0ms · 0/0 tok · $0.0000` (mock has no
  usage/cost) — the *shape* is verified, not live numbers.
- **CI serve-extra fix (orchestrator).** `mypy --strict src` requires the `mcp` SDK to typecheck
  `serve/mcp_server.py`. The orchestrator CI synced only `--extra chroma`, so the type-check leg was
  red (`import-not-found` on `mcp`). Fixed in `c951030`: `uv sync … --extra serve`. Type-checking and
  testing code that uses an optional extra requires that extra installed.
- **Lab-venv preflight: `mcp>=1.27.2` + `typer==0.26.2`.** Installed `mcp` into the lab venv (it
  predated the optional `[serve]` extra). Also pinned `typer==0.26.2` to match the orchestrator lock —
  see KI-R5-01.
- **KI-R5-01 — version-fragile `Result` ignore.** `src/lottie/cli/tests/test_knowledge.py` imports
  `Result` from `typer.testing`, which typer **0.26.2** does not list in `__all__` (mypy
  `attr-defined`) but **0.26.3** does. The orchestrator carries `# type: ignore[attr-defined]`, which
  is *required* under the locked 0.26.2 but flagged **unused** under 0.26.3 (`warn_unused_ignores`).
  CI passes (lock pins 0.26.2); the lab venv was pinned to 0.26.2 to verify against the same env. A
  `uv lock --upgrade` that bumps typer to 0.26.3 would flip this — track for the REST slice.
- **Coverage of the stdio loop.** `serve/mcp_server.py` is 91% — the uncovered lines are the real
  blocking stdio loop (`_run_stdio` body, the `_run_stdio_blocking` call) and the description fallback
  (lab agents all ship prompts). The loop is exercised structurally via the `_run_stdio_blocking`
  seam test, not by spawning a real stdin.
