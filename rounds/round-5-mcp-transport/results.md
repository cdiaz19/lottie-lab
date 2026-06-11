# Round 5 — Results: MCP stdio Transport (Phase 4 slice 1)

**Code under test:** `lottie-orchestrator` `feat/mcp-stdio` @ `c951030` (PR #6)
**Date:** 2026-06-10 · **venv:** `lottie-lab/.venv` (py 3.12.13, pytest 9.0.3) · **providers:** Mock (API keys UNSET)
**Raw data:** `outputs/` (A-mcp-server, B-cli-serve, C-serve-core, mypy, ruff, full-suite, coverage, input-*.out.json)

> Run from `lottie-orchestrator` (installed `-e` into the lab venv). Preflight: `mcp>=1.27.2`
> installed into the venv (it predated the optional `[serve]` extra), and `typer` pinned to
> `0.26.2` to match the orchestrator lock (see KI-R5-01).

---

## 1. Test groups

| Group | Command | Result |
|-------|---------|--------|
| A — MCP server (list_tools / call_tool / serve_stdio) | `pytest src/lottie/serve/tests/test_mcp_server.py` | ✅ **6 passed** |
| B — `lottie serve` CLI (install hint + wiring) | `pytest src/lottie/cli/tests/test_serve.py` | ✅ **2 passed** |
| C — serve-core regression (AgentService + gate) | `pytest src/lottie/serve` | ✅ **22 passed** |
| Full suite | `pytest -q` | ✅ **618 passed** |
| Type check | `mypy --strict src` | ✅ **no issues (132 files)** |
| Lint | `ruff check .` | ✅ **All checks passed** |

---

## 2. Input cases (`run-inputs.sh` → `outputs/input-*.out.json`)

| Case | Op | Status | Actual | Note |
|------|----|--------|--------|------|
| input-01-list-tools | `list_tools` | ✅ pass | `digest`, `reviewer` — each `inputSchema.properties = ["query"]` | one typed tool per agent, schema from `Input` model |
| input-02-call-digest | `call_tool digest {query}` | ✅ pass | `isError=false`; `structuredContent={"result": …}`; content `[lottie] 0ms · 0/0 tok · $0.0000` | output as structured + metrics line (mock → zero usage) |
| input-03-call-reviewer | `call_tool reviewer {query}` | ✅ pass | `isError=false`; `structuredContent={"result": …}` | per-agent routing — `reviewer` runs, not `digest` |
| input-04-bad-payload | `call_tool digest {wrong}` | ✅ pass | `isError=true`; content = Pydantic `query Field required` | `InvalidInputError` → `isError` (run_agent is sole validator) |
| input-05-unknown-tool | `call_tool nonexistent` | ✅ pass | `isError=true`; `agent 'nonexistent' not found` | `AgentNotFoundError` → `isError` (defensive path) |

---

## 3. Tool registration & schema (group A)

- [x] `build_mcp_server(root)` registers one `types.Tool` per discovered agent (`digest`, `reviewer`).
- [x] Each tool's `inputSchema == load_input_model(root, name).model_json_schema()` (verified in suite + live `list_tools`).
- [x] A broken/unimportable agent is logged and **skipped** — server still builds, healthy agents still list (`test_broken_agent_is_skipped`).
- [x] Tool `description` is the first system-prompt line, with a `Run the <name> agent.` fallback.

## 4. call_tool — run, return, errors (group A)

- [x] Sync `run_agent` threadpool-wrapped via `anyio.to_thread.run_sync` (no async churn in `BaseAgent`/core).
- [x] Success → `structuredContent = output dict` + a trailing `[lottie] …ms · …/… tok · $…` text line. Output dict only; metrics never pollute the structured view.
- [x] `validate_input=False` → `run_agent`'s Pydantic `Input` validation is the sole authority (input-04 reaches it and raises).
- [x] Error mapping, every `ServeError` → MCP `isError`:
  - [x] bad payload → `InvalidInputError` → `isError` (input-04)
  - [x] unknown tool → `AgentNotFoundError` → `isError` (input-05)
  - [x] agent raises → `AgentExecutionError` → `isError` (suite `test_call_tool_execution_error_is_error`)
  - [x] load failure → `AgentLoadError` → `isError` (defensive; covered generically by `except ServeError`)

## 5. serve_stdio + CLI (groups A, B)

- [x] `serve_stdio(root)` builds the server and hands it to `_run_stdio_blocking` (patchable seam — `test_serve_stdio_runs_built_server`).
- [x] `lottie serve` registered; appears in `lottie --help`.
- [x] Missing `[serve]` extra → clean `BadParameter` with `pip install lottie-orchestrator[serve]` (no traceback) — `test_serve_missing_mcp_shows_install_hint`.
- [x] Present → `serve_stdio(find_project_root())` invoked with the resolved root — `test_serve_invokes_serve_stdio_with_project_root`.

## 6. Optional-dep hygiene & regression

- [x] `import lottie.serve` works **without** `mcp` — `serve/__init__.py` never imports `mcp_server`.
- [x] `mcp` imported only in `serve/mcp_server.py` (module top), reached lazily through the CLI.
- [x] `mcp` is an optional `[serve]` extra in `pyproject.toml`, not a base dependency.
- [x] Round-3 serve-core contract intact (22 passed): `list_agents` import-free, typed error hierarchy, identity `SecurityGate` chokepoint runs input-before-output on every run.

## 7. Definition of done — checklist

- [x] One typed MCP tool per healthy agent; schema from each `Input` model; broken agents skipped.
- [x] `call_tool` returns output as `structuredContent` + a metrics text line.
- [x] Every `ServeError` → `isError`; `run_agent` is the sole input validator.
- [x] `lottie serve` runs the stdio loop; friendly install hint when `[serve]` absent.
- [x] `import lottie.serve` does not require `mcp`; `mcp` is an optional extra.
- [x] Full suite green (618), `mypy --strict` (132) + `ruff` clean.
- [x] Serve-package coverage: `service.py` 100%, `security.py` 100%, `cli/serve.py` 100%, `mcp_server.py` 91% (uncovered = the real blocking stdio loop + the description fallback).

**Round 5 = MCP stdio transport verified.** → merge `feat/mcp-stdio` (PR #6) to `main`; open Round 6 (REST + OpenAI-compat → shared ASGI app → `lottie serve --port`).

---

## Known issues

- **KI-R5-01 — version-fragile `typer.testing.Result` ignore.** `src/lottie/cli/tests/test_knowledge.py`
  imports `Result` from `typer.testing`. typer **0.26.2** omits it from `__all__` → mypy
  `attr-defined`, so the file carries `# type: ignore[attr-defined]`. typer **0.26.3** exports it →
  the ignore is **unused** and `warn_unused_ignores` (part of `--strict`) fails. Orchestrator CI passes
  because the lock pins 0.26.2; the lab venv was pinned to 0.26.2 to match. **Risk:** a
  `uv lock --upgrade` bumping typer to 0.26.3 flips the gate red. Carryover from KI-R4-01 (which fixed
  the *runtime* import but not the strict-mypy follow-on). Resolve in the REST slice — e.g. a
  version-robust import or a typer pin.
- **CI was red before this round.** Orchestrator CI synced only `--extra chroma`, so `mypy --strict src`
  hit `import-not-found` on `mcp`. Fixed in `c951030` (`--extra serve`); the fix is part of PR #6.
