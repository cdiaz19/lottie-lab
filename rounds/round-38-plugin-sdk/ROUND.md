# Round 38 — Plugin SDK (orchestrator E7)

> E7 freezes a **public** extension API, so this round is written from the position of
> someone who might abuse it. A plugin runs **in-process with the host's privileges and is
> not sandboxed** — the only real lever is how much of the system it is handed, and every
> case here probes that boundary.

| # | Case | Result |
|---|------|--------|
| 1 | a well-behaved plugin receives real events | PASS |
| 2 | **a plugin cannot read the task** | PASS |
| 3 | **a plugin cannot read the output** | PASS |
| 4 | **a middleware-shaped plugin is refused at load** | PASS |
| 5 | **a plugin never enters the middleware chain** | PASS |
| 6 | a plugin that raises cannot fail the run | PASS |
| 7 | it cannot starve the next plugin | PASS |
| 8 | it cannot displace the audit record | PASS |
| 9 | a non-subscriber is refused by shape | PASS |
| 10 | **nothing loads that the config did not name** | PASS |
| 11 | an unimportable plugin fails loudly, not silently | PASS |

## Case 5 is the one that actually holds the line

The load-time `isinstance(instance, Subscriber)` check is a friendly early error — Python's
`runtime_checkable` only verifies *method presence*, so a determined author could satisfy
it. The real guarantee is structural: **a plugin only ever reaches `bus.subscribe` and
never enters `build_chain`.** Even a class shaped like middleware cannot intercept,
because nothing ever mounts it as one.

Case 4 confirms the friendly error still fires, and that it explains *why* — an author who
tries to ship middleware deserves the reason, not just a refusal.

## Cases 2 and 3 are the confidentiality bound

Events carry scalars and hashes only. The round runs a task containing
`SENSITIVE_TASK_TEXT` and asserts it appears in no event a plugin receives. Third-party
code in the process cannot read what the agent was asked or what it answered.

## Cases 6–8 are the availability bound

A plugin that raises on **every** event: the run still completes and returns its real
answer, the next plugin still receives its events, and the audit record still lands.
Plugins subscribe *after* the audit subscriber, and the bus isolates every dispatch.

## Case 10 — no discovery

Nothing loads that the config did not name. There is no entry-point table to enumerate and
no namespace for a package to squat in; a plugin class sitting in an imported module is
inert until something names it by explicit path.

## Run

```bash
.venv/bin/python rounds/round-38-plugin-sdk/_plugin_driver.py
```

## Result

**11/11 PASS** against orchestrator `feat/e7-plugin-sdk`.
Lab CI remains red on `ORCH_REPO_TOKEN` — known non-bug, see repo README.
