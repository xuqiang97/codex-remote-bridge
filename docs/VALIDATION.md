# Validation Record

This file must separate planned checks from checks that were actually executed.

Do not mark V1 complete based only on unit tests.

## Current status

**No-Go for the tested Desktop-open Windows handoff, 2026-09-20.**

Phase 0 and the Phase 1 handoff probe were executed. A separate app-server could
read a completed Desktop test thread, but could not resume it: two fresh-process
attempts returned `-32600`, `already has an active writer`. No bridge turn was
started. Full implementation is stopped, as required by the gate and the owner.

Only this record and README were changed. No DingTalk credentials were requested
or used. No production bridge, offline suite, or CI workflow was implemented.
No scope change to bridge-managed threads has been approved.

## Gate A — Desktop thread -> app-server resume

**Status: FAIL / No-Go in the tested environment.**

### Environment and provenance

| Item | Observed value |
| --- | --- |
| OS | Windows, build 10.0.26100, x86_64 |
| Desktop package | OpenAI.Codex 26.915.4065.0 |
| CLI / child app-server | codex-cli 0.155.0-alpha.9.2 |
| Python | 3.14.5 |
| Source revision tested | 04251c5 |
| Executable | Desktop-managed codex.exe resolved from PATH; same executable as the running Desktop server |
| OS identity | Desktop server process owner matched the invoking OS user; probe inherited that user's environment |
| Codex home | CODEX_HOME unset; initialize returned the same user's default Codex home; the real Desktop thread was readable there |
| Transport | New local child process, stdin/stdout pipes; stderr separately drained; no network listener |
| Experimental API | Not enabled in initialize; schema generated without --experimental |
| Test repository alias | bridge-handoff-safe-test; fresh disposable local Git repository |

Personal paths, full thread/turn IDs, OS account names and raw protocol responses
are intentionally not published. This alpha build is the actual installed
version; this test makes no claim about other Codex releases or macOS.

### Executed procedure

1. Read AGENTS, SECURITY, IMPLEMENTATION, PROTOCOL, DECISIONS, VALIDATION and
   README, then the remaining tracked configuration/license files.
2. Resolve `codex`, run `codex --version`, inspect app-server help, and generate
   the installed stable schema with `codex app-server generate-json-schema --out
   schemas`. Generated schemas are Git-ignored.
3. An initial Desktop worktree task remained in queued setup and did not provide
   a usable thread ID. It is not counted as the baseline. Create a separate
   Desktop projectless task using the supported app task-creation tool instead.
   The task initializes a disposable Git repository and writes only README.md
   containing `bridge handoff disposable fixture`.
4. Give that task a harmless conversation-only marker and integer, absent from
   the repository file. Desktop replies `DESKTOP_BASELINE_READY` and ends its
   turn. The app's wait/read tools confirm `completed`, no error, and thread
   status `idle`. Obtain the real thread ID from the supported task-creation
   response, not from internal storage.
5. Start a fresh `codex app-server` via Python asyncio subprocess, without a
   shell or listener arguments. Complete initialize/initialized in order.
6. Send `thread/read` with includeTurns=true. It succeeds, returns the baseline
   turn/history, and reports status `notLoaded` in this independent process.
7. Send `thread/resume` with approvalPolicy=never and sandbox=workspace-write.
   It fails with the exact error below. Do not call `turn/start` after failed
   resume. Close stdin and wait for child exit.
8. Reconfirm Desktop is idle and the baseline completed. Repeat with another
   fresh child process: initialize and read succeed; resume fails identically.
9. Read the disposable README and Git status: fixture content unchanged, only
   the expected untracked README. Desktop still displays the completed baseline.
10. After both child processes exit, send a no-tool follow-up through Desktop
    asking for the remembered marker and the original integer plus five, without
    repeating either value. Verify Desktop continuation separately below.

### Exact request shapes and results

`<TEST_THREAD_ID>` below is a documentation placeholder. Replay only against a
dedicated, completed test task, under its Desktop OS user and Codex home.

```json
{"id":1,"method":"initialize","params":{"clientInfo":{"name":"bridge_gate_probe","version":"0.0.1"}}}
{"method":"initialized","params":{}}
{"id":2,"method":"thread/read","params":{"threadId":"<TEST_THREAD_ID>","includeTurns":true}}
{"id":3,"method":"thread/resume","params":{"threadId":"<TEST_THREAD_ID>","approvalPolicy":"never","sandbox":"workspace-write"}}
```

Both resume attempts returned:

```json
{"id":3,"error":{"code":-32600,"message":"thread <TEST_THREAD_ID> already has an active writer"}}
```

The installed stable schema uses `workspace-write` for `ThreadResumeParams.sandbox`
and `workspaceWrite` for `TurnStartParams.sandboxPolicy.type`. The probe used the
installed schema's correct resume spelling; this was an ownership error, not an
invalid enum response.

| Check | Actual result |
| --- | --- |
| Completed real Desktop baseline | PASS |
| Supported thread ID discovery | PASS |
| Independent stdio initialization | PASS, twice for target test |
| thread/read | PASS, one baseline turn returned in both attempts |
| thread/resume | FAIL, active-writer error in both attempts |
| Child turn/start | NOT RUN because resume failed |
| Cross-client conversation continuity | NOT PROVEN |
| Desktop display after attempts | PASS via supported task read |
| Desktop follow-up continuity | PASS: exact marker recalled and 137 + 5 returned as 142; completed without tools |
| Repository behavior | Fixture unchanged; no bridge tool execution |
| Duplicate child turn / ownership takeover | None started; writer conflict rejected at resume |

### Failure interpretation and safety limits

Observed: completion of the Desktop turn did not make this thread available to a
separate writer while Desktop remained open. The error establishes a writer
conflict. It does not establish whether the cause is intended Desktop lifetime
ownership, a release-specific behavior, or a defect.

A separate read-only diagnostic also compared an actively running Desktop task
with independent `thread/read`: the independent server reported `notLoaded`.
No resume/start/interrupt was sent for that active task. Therefore `notLoaded`
must not be treated as proof that another client has no active turn. Reliable
cross-client ownership detection remains unresolved for the V1 security model.

No rollout, Codex database, lock, or unpublished state file was edited or parsed
to bypass ownership. No Desktop process was killed, no experimental API was
enabled, no prohibited shell/exec RPC was invoked, and no public listener was
opened. Raw probe artifacts remain local in Git-ignored directories.

Next step is an owner-led architecture discussion. A documented release/handoff
mechanism, a separately authorized Desktop-closed test, and bridge-managed-only
threads are possible discussion topics, not implemented workarounds or accepted
scope changes. No full development should resume on the strength of read-only
success alone.

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

No workflow exists at the tested revision. Windows/macOS CI is not run because
the mandatory pre-implementation gate failed. This is not a passing CI result.
The public GitHub Actions runs API was checked on 2026-09-20 and returned zero
workflow runs.

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

Partial documentation-only review on 2026-09-20: all ten existing commits and
eleven unique tracked tree entries were scanned for common API-token/private-key
patterns and this machine's personal-path/private-host patterns, with no matches.
All tracked files were read; the only configuration values are empty values and
documented examples. Existing commit author emails are GitHub noreply metadata.
This bounded review is not a comprehensive secret-scanner guarantee or V1 runtime
security acceptance. Local probe outputs and generated schemas are ignored and
must not be force-added.

`git diff --check` passed for the documentation change. There is no application
test suite to run at this architecture-only revision.

### Publication

GitHub push preflight and the actual post-commit push both returned HTTP 403: the locally authenticated account does
not have write access to the repository. Credentials were not printed, changed,
or committed. The owner must grant repository write access or authenticate an
authorized account locally before publication can complete. No fork, pull request,
or history rewrite was used to bypass the requested destination.

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
