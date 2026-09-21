# Validation Record

## Coordinator acceptance update — 2026-09-21

**Scope:** Owner requested a persistent DingTalk coordinator for open-ended task
queries, work assignment into existing tasks, and proactive completion replies.
This supersedes the manual `/use` prerequisite. Implementation is an acceptance
build, not a fully validated release.

### Real local evidence

- Production AppServer client resumed the completed Desktop fixture under the same
  Windows user/home and recalled its conversation-only marker with the correct
  arithmetic follow-up (original integer plus thirteen).
- First sandboxed file-write canary timed out after 120 seconds and was interrupted
  when the owned child closed. It produced no file; the failure is retained here.
- A second explicit local canary, with low reasoning effort and a 300-second wait,
  completed a native commandExecution and created only the requested canary file
  with the exact expected content. No approval request or elevation was accepted.
  Existing task model identity was not changed. This was a separate operator test,
  not an automatic retry of an uncertain DingTalk event.
- Stable `thread/start` + `thread/name/set` created the persistent `钉钉机器人`
  task. It returned structured read-only answers based on allowed task summaries.
- A fresh process reused that same coordinator. It dispatched one verbatim,
  no-tool follow-up into the existing Desktop fixture; the returned marker and
  original integer plus seventeen were both correct. The target completed and
  the router delivered its named final response to the test callback.
- The first dispatch proposal was safely rejected because an overly broad negative
  phrase check treated “Do not use tools” inside the work instruction as rejection
  of dispatch. The check now examines the authorization prefix; an offline regression
  case covers safety constraints inside the instruction.
- The official proactive DingTalk private-message API accepted a coordinator-ready
  notification to the already-authorized initiating user. No invalid/rate-limited
  recipients were returned. This proves API acceptance, not human reading.
- The updated Stream bridge reconnected. An actual inbound message -> coordinator
  -> target -> DingTalk final loop still needs the owner's real chat confirmation.
  Local router injection must not be reported as that full-channel acceptance.

### Automated checks and limits

All 48 offline tests passed on Windows/Python 3.14.5. Compile checks, configuration
validation and git diff whitespace checks passed. The release audit scanned 24
candidate files and all 11 pre-implementation commits for the actual local secret,
user-ID and personal-path values plus common key patterns: no matches. This is
a bounded scan, not a guarantee that every possible sensitive string is detected.
GitHub Actions API reports zero runs; the workflow has not been remotely validated.

The offline suite now covers coordinator creation/reuse, structured stable RPC
shapes, read-only policy, filtered history, query-vs-dispatch safety, unique targets,
verbatim instructions, negative/hypothetical messages, duplicate callbacks,
foreign active ownership, completion reporting, restart unknown outcomes and
proactive recipient allowlisting/token reuse/rate-limit handling.

Task context is bounded: at most 200 allowed tasks in the coordinator catalog,
12 recent tasks preloaded with 3 recent final results each. This is not a complete
all-day activity audit. Ambiguous/unsupported phrasing asks for clarification.
Restart preserves coordinator/binding/dedupe state and dispatch identifiers, but
marks interrupted in-flight ownership unknown; it never replays work or automatically
reconciles missed completion notifications. Query the target again after restart.
Desktop writer conflicts remain fail-closed. Windows live remote-stop/elevation/
duplicate-event tests and macOS live acceptance remain outstanding.


This file must separate planned checks from checks that were actually executed.

Do not mark V1 complete based only on unit tests.

## Current status

**2026-09-21: conditional Go for released existing threads; V1 implementation
is present, final real end-to-end acceptance is pending.**

The 2026-09-20 No-Go below remains valid evidence for a Desktop-owned thread.
On 2026-09-21 the same real test thread was no longer loaded by Desktop and
could be resumed independently. A real follow-up recalled its conversation-only
marker and correctly used the original number. The production asynchronous
client subsequently passed a second continuity canary. No internal state was
modified to obtain either result. What released Desktop ownership is unknown.

The owner reaffirmed existing-task support and authorized implementation for
other Windows users, plus access to the current project on this machine.
No bridge-managed-only rescope, force takeover or remote approval is implemented.
The release still cannot promise availability of every Desktop task at any time.

## Gate A — Desktop thread -> app-server resume

**2026-09-20 result: FAIL while Desktop held the writer.**

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

### 2026-09-21 repeat: successful existing-thread continuation

Same OS, Python, Codex CLI and Desktop package as above. The app's supported
task status tool now reported the disposable baseline thread as `notLoaded`,
with its two original completed turns preserved. No process was stopped and
no lock, database or rollout was changed to cause this state.

1. A new independent stdio process initialized and read the same stored task.
2. `thread/resume` with never/workspace-write succeeded and returned idle.
3. `turn/start` used approvalPolicy=never and sandboxPolicy workspaceWrite,
   networkAccess=false, no extra writable roots, and excluded temporary roots.
4. The prompt requested recall of the original codeword and original integer
   plus nine, without repeating the codeword or integer. Only a text response
   was requested; tool access was explicitly unnecessary.
5. The completed agent message returned the exact codeword and `146` (137 + 9).
   `turn/completed` reported completed, no error, duration 19,459 ms. No tool or
   approval request occurred. The disposable README/Git state remained unchanged.
6. After closing the child, Desktop's supported read API displayed the new
   completed Turn. Its compact item list was empty, so this proves Desktop
   recognizes the Turn, not a full graphical UI rendering check.
7. After implementing `codex_bridge/app_server.py`, a separate real canary used
   that production client, local allowlisted config, `thread/read`,
   `thread/resume`, and `turn/start`. It requested original integer plus thirteen
   and got the exact marker with `150`, completed, no denied request. This is
   a real Codex client test, not an offline test and not a DingTalk inbound test.

**Conclusion:** continuation of a released existing Desktop task is proven on
this version. Simultaneous takeover of a Desktop-owned task is neither supported
nor attempted. The earlier idle-writer refusal and active/notLoaded discrepancy
remain important limits; successful server writer acquisition is required.

Local CLI help also exposed `app-server proxy` and `app-server daemon version`.
The read-only daemon version query failed on the default control socket with
OS error 10050. No daemon was started/reconfigured and no alternate hidden
Desktop socket was accessed. This is not a validated transport alternative.

## Gate B — Offline automated tests

**Status:** 48 offline tests passed on local Windows / Python 3.14.5.

Command: `.venv/Scripts/python -m unittest discover -s tests -v`.
Compile check and `git diff --check` also passed. Protocol tests use in-memory
fake streams/processes; routing tests use a fake app and fake replies. No real
Codex, DingTalk, shell or thread store is used. External socket connects are
blocked; loopback is permitted for Windows asyncio's internal socketpair.

Record:

- test command;
- test count;
- Python versions;
- Windows result;
- macOS result;
- network isolation approach.

## Gate C — Public CI

**Status:** Pending

The workflow now exists at `.github/workflows/ci.yml`, with the required matrix.
It has not run on GitHub: a fresh push preflight still returns HTTP 403 for the
locally authenticated account. Do not infer passing CI from local tests.
The last checked public Actions runs API returned zero workflow runs.

Required matrix:

- Windows + Python 3.10;
- Windows + current Python;
- macOS + Python 3.10;
- macOS + current Python.

Record workflow URL/commit and outcome.

## Gate D — DingTalk Stream

**Status:** Core private receive/reply passed on Windows, 2026-09-21.

The owner explicitly authorized a standalone robot connectivity test after the
Desktop handoff No-Go. This does not reopen full V1 implementation or change its
Codex ownership gate. A bounded local diagnostic uses official `dingtalk-stream`
0.24.3, Python 3.14.5 and websockets 17.1 in an ignored virtual environment.

Executed results:

- OAuth application-token request: HTTP 200, access token present (not logged).
- Stream connection-ticket request for the chatbot callback topic: HTTP 200,
  endpoint and ticket present (not logged).
- Secure WebSocket connection established successfully.
- After the owner explicitly supplied their own enterprise UserID and requested
  a proactive test, send exactly one fixed `sampleText` message using
  `/v1.0/robot/oToMessages/batchSend`. HTTP 200, processQueryKey present,
  zero invalid recipients and zero rate-limited recipients. This proves API
  acceptance, not user-visible delivery. No automatic send retry was used.
- The supplied stable sender ID is configured only in the ignored local test
  allowlist. The listener accepts the exact private test challenge from that
  sender for a single fixed reply; other senders cannot trigger a reply.
- A real private text callback arrived, matched the exact challenge and the
  configured sender ID. The fixed session-webhook reply returned HTTP 200 and
  errcode=0. No Codex was attached to that smoke test. User-visible display of
  the reply was not independently inspected.
- SDK raw logging disabled to prevent credentials, tickets or callback bodies
  entering logs; only explicit diagnostic outcome fields are emitted.
- Diagnostic accepts no Codex commands and opens no inbound port. It waits up
  to ten minutes for a private test message. An unapproved sender receives no
  reply; a local sender/conversation allowlist is required for the fixed test
  response. No ordinary message content is stored.
- Diagnostic source, local credentials and any sender identifiers are confined
  to ignored local files, not tracked files or SQLite.

Not yet verified live: unauthorized-sender canary, forced network reconnect,
duplicate platform event, or the complete DingTalk-to-Codex-to-DingTalk Turn.
Authorization/deduplication have offline coverage in the implemented bridge.

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

The implemented Bridge has started successfully with local ignored credentials,
the owner's allowed user and two explicit allowed roots (current project and
the disposable test repository). The new Stream connection succeeded. The owner
was asked to run `/threads`, bind the disposable task and request original
integer plus eleven. Await actual callback/start/final-response evidence before
marking this gate passed. Merely starting the bridge is not this gate.

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

At the historical documentation-only revision, `git diff --check` passed and no
application suite existed. The current implementation has an offline suite; see
the coordinator update and Gate B for its current validation status.

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
