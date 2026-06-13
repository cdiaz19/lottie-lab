# EditorMesh

## Role

Reference **content-pipeline mesh**: a `MeshAgent` subclass (from `lottie.mesh`) that routes a single task through a fixed editorial workflow — plan, parallel draft + factcheck, review, and a **human-in-the-loop publish gate**. The injected LLM acts as the **supervisor**, picking the next worker at each step; the engine loops until the supervisor returns `FINISH` or `max_steps` is reached.

`publish` is declared in `interrupt_before`, so this mesh always requires the **`[mesh]` extra** (LangGraph engine + checkpointer).

## Topology

```
            ┌──> draft ─────┐
plan ──> (parallel)         ├──> review ──> [HITL gate] ──> publish ──> FINISH
            └──> factcheck ─┘
```

## Input

| Field | Type | Default | Description |
|---|---|---|---|
| `task` | `str` | — | The task to route through the content pipeline |
| `max_steps` | `int` | `8` | Hard cap on routing steps before the loop ends |

`EditorInput` is a discovery-named alias over `MeshInput`.

## Output

| Field | Type | Description |
|---|---|---|
| `final` | `str` | The final answer assembled by the mesh run |
| `history` | `list[StepResult]` | Ordered record of each worker invocation (`worker`, `result`) |
| `status` | `str` | `"ok"` or `"interrupted"` (paused at HITL gate) |
| `thread_id` | `str` | Checkpoint thread ID, needed for resume |
| `pending` | `PendingApproval \| None` | Set when status is `"interrupted"` |

`EditorOutput` is a discovery-named alias over `MeshOutput`.

## Workers (capability allow-set)

```yaml
workers:
  - plan
  - draft
  - factcheck
  - review
  - publish
```

The `workers:` list in `config.yaml` is the **capability allow-set**: the exact routing roster the supervisor may pick from. It must match the keys of `_DESCRIPTIONS` in `agent.py`. Anything outside this set is a capability violation.

| Worker | Role | Deterministic output |
|---|---|---|
| `plan` | Outlines a short plan for the task | `PLAN: <task>` |
| `draft` | Writes a draft answer | `DRAFT: <task>` |
| `factcheck` | Checks the draft's facts | `FACTCHECK: ok` |
| `review` | Reviews the drafted work and approves it | `REVIEW: approved` |
| `publish` | Publishes/finalizes the reviewed answer | `PUBLISHED: <task>` |

## Human-in-the-Loop (`interrupt_before`)

`publish` is listed in `interrupt_before`, so the run **always pauses before publishing**. When the supervisor routes to `publish`, the engine checkpoints state and `mesh.run(...)` returns `MeshOutput` with `status="interrupted"` and a populated `pending` (`PendingApproval(worker="publish", ...)`). No publish call has happened yet. The caller then resumes:

```python
from agents.editor.agent import EditorMesh
from agents.editor.schema import EditorInput
from lottie.mesh.schema import ApprovalDecision

mesh = EditorMesh.from_project(llm=llm, root=root, config=config)
out = mesh.run(EditorInput(task="Write a short post on async Python."))
if out.status == "interrupted":
    resumed = mesh.resume(out.thread_id, ApprovalDecision(action="approve"))
    # action="approve"  — runs the publish node and continues the loop
    # action="reject"   — records rejection without executing the worker
```

Because `interrupt_before` is non-empty, `from_project` always builds the mesh on the `LangGraphEngine`. This requires the **`[mesh]` extra**:

```bash
pip install lottie-orchestrator[mesh]
```

If the extra is absent, `from_project` raises `MeshError` with a clear install message.

## Design Note: Pure Workers, Single LLM Consumer

All five workers are **pure and deterministic** — they do no LLM calls and produce stable outputs. The **supervisor router is the only LLM consumer** in this mesh; it is constrained to the declared `workers:` set. An undeclared routing choice raises `CapabilityViolation`. This makes the mesh ideal for verifying routing logic and HITL mechanics without flaky LLM outputs.

## Provider

Default: `anthropic/claude-sonnet-4-6` (supervisor LLM). Workers receive the same injected LLM instance but do not use it.

## Policies

- `base`

## CLI

Reuses the existing stack — **no new CLI**:

```bash
lottie run editor               # run the content pipeline (pauses at publish gate)
lottie serve                    # exposes editor as an MCP tool
lottie benchmark agent editor
```
