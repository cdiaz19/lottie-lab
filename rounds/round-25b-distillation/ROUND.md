# Round 25b — Skill distillation (orchestrator V2 S3b)

> Validate the SHIPPED distillation chain end-to-end from a downstream project, against a
> **real `SqliteMemoryClient` on disk**.

## What's being tested

The full chain, with nothing stubbed but the LLM:

```
agent runs → S3a trajectory persistence → distillation → gated draft on disk
                                                       → TemplateRunnerSkill executes it
```

S3b's central security claim is that distillation adds **no arbitrary-execution surface**:
a distilled skill is a prompt template, never Python. Cases 5–7 attack that claim directly.

| # | Case | Checks |
|---|------|--------|
| 1 | corpus | 3 real agent runs → 3 readable trajectories |
| 2 | draft write | `template.yaml` + `provenance.yaml` + `SKILL.md` under `skills/draft/` |
| 3 | round-trip | template and provenance survive disk |
| 4 | execution | `TemplateRunnerSkill` renders and runs it |
| 5 | **no code** | draft contains **zero** `.py` files — it is data, not an importable module |
| 6 | **write gate** | injected template (`<\|im_start\|>`) rejected, nothing on disk |
| 7 | **no `str.format`** | attribute-traversal placeholder stays inert text |
| 8 | slot contract | missing required slot fails closed |
| 9 | versioning | re-distill bumps the minor version |

### Why case 7 exists

`"{q.__class__.__init__.__globals__}".format(q=obj)` is a well-known Python info-leak: it
walks attributes to reach the module globals, which can contain secrets. A distilled
template is **LLM-authored**, so if rendering used `str.format` the model could author that
traversal and read process memory on every invocation.

S3b renders by literal replacement of declared slots only. The round asserts the traversal
placeholder survives as literal text with the declared slot filled and no object `repr`
(`0x…`) leaking in — the exact evidence that `.format` is not in the path.

## Run

```bash
.venv/bin/python rounds/round-25b-distillation/_distill_driver.py
```

## Result

**9/9 PASS** against orchestrator `feat/v2-s3b-distillation`.

```
PASS  1. S3a trajectories are readable as a distillation corpus — trajectories=3
PASS  2. draft written to skills/draft/ with template + provenance + SKILL.md
PASS  3. draft round-trips with provenance intact — agent=digest, n=3
PASS  4. TemplateRunnerSkill executes the distilled template — version=0.1.0
PASS  5. draft contains NO Python — it is data, not an importable module — py_files=[]
PASS  6. injected template rejected by the write gate, nothing on disk — blocked=True
PASS  7. attribute-traversal placeholder cannot leak (no str.format) — traversal left as literal text
PASS  8. missing required slot fails closed
PASS  9. re-distill bumps the minor version
```

Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.

## Not covered here

`lottie distill review` (HITL promotion draft→registered, capability declared at promotion)
is orchestrator slice **S3c** and gets round **R25c**.
