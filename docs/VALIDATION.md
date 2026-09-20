# Validation Record

This file must separate planned checks from checks that were actually executed.

Do not mark V1 complete based only on unit tests.

## Current status

Architecture/specification only.

No implementation, DingTalk credential, Codex app-server handoff test, or real remote turn has been validated in this repository yet.

## Gate A — Desktop thread -> app-server resume

**Status:** Pending

Required evidence:

- OS:
- Codex Desktop version:
- Codex CLI/app-server version:
- Python version:
- test repository:
- Desktop thread completed:
- thread ID identified:
- `thread/read` result:
- `thread/resume` result:
- follow-up `turn/start` result:
- previous-context continuity confirmed:
- Desktop can still display/use thread afterward:
- concurrent ownership issue observed:
- Pass/Fail:

This gate must pass before claiming the product can continue an existing Desktop conversation.

## Gate B — Offline automated tests

**Status:** Pending

Record:

- test command;
- test count;
- Python versions;
- Windows result;
- macOS result;
- network isolation approach.

## Gate C — Public CI

**Status:** Pending

Required matrix:

- Windows + Python 3.10;
- Windows + current Python;
- macOS + Python 3.10;
- macOS + current Python.

Record workflow URL/commit and outcome.

## Gate D — DingTalk Stream

**Status:** Pending

Validate with safe bot credentials:

- Stream connection starts;
- reconnect after network interruption;
- direct text received;
- reply sent;
- sender stable ID observed;
- conversation ID observed;
- unauthorized sender denied;
- duplicate message does not duplicate side effect.

Do not record credentials or full personal IDs in this public document.

## Gate E — Thread authorization

**Status:** Pending

Validate:

- allowed project appears in `/threads`;
- unallowed project does not appear;
- full local paths not displayed;
- stale `/use` index rejected;
- binding survives restart.

## Gate F — End-to-end Windows

**Status:** Pending

Required path:

```text
DingTalk
 -> local Stream bridge
 -> codex app-server
 -> existing allowed thread
 -> turn/start
 -> final agent response
 -> DingTalk
```

Record:

- device alias:
- OS:
- Codex version:
- DingTalk SDK version:
- Python:
- project alias:
- one remote follow-up starts exactly one turn:
- result returned:
- latency observation:
- `/stop` works only for bridge-owned turn:
- remote elevation attempt safely denied:
- Pass/Fail:

## Gate G — End-to-end macOS

**Status:** Pending

Same evidence as Windows.

## Gate H — Security acceptance

**Status:** Pending

Confirm:

- no secrets in tracked files/history;
- no public app-server listener;
- experimental API off;
- sender allowlist required;
- project-root allowlist required;
- no remote approval path;
- no shell/exec command;
- dedupe durable;
- logs exclude full prompt/output/path/credential data;
- SQLite excludes credentials/conversation content.

## Release status

V1 should be labeled validated only after the required real-environment gates are complete.

If Desktop-thread handoff fails but the project is re-scoped to bridge-managed threads, update `README.md`, `AGENTS.md`, `DECISIONS.md`, and this record before implementation continues.
