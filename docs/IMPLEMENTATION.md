# V1 Implementation Plan

Read `AGENTS.md` and `SECURITY.md` first.

This plan is intentionally phased. Do not skip the handoff validation and jump directly to DingTalk bot work.

## Phase 0 — Environment and schema discovery

On each target machine:

1. verify `codex` executable location/version;
2. verify `codex app-server` starts;
3. generate/read app-server schema for the installed version if useful;
4. confirm Python version;
5. confirm same OS user/CODEX_HOME as Codex Desktop;
6. record results in `docs/VALIDATION.md`.

Do not commit personal paths or secrets.

## Phase 1 — Desktop-thread handoff spike

Goal:

> Prove that a completed thread used by Codex Desktop can be resumed by a new local app-server process and continued.

Use a disposable/safe repository.

### Procedure

1. In Codex Desktop, run a harmless request such as creating/reading a test file.
2. Wait for the turn to complete.
3. identify the stored thread ID using a supported mechanism.
4. launch a minimal app-server client.
5. send `initialize`, then `initialized`.
6. call `thread/read` and/or `thread/resume`.
7. confirm expected thread metadata/history context.
8. call `turn/start` with a harmless follow-up.
9. verify the reply reflects the previous conversation.
10. inspect the Desktop thread after the operation if possible.
11. verify no corruption or duplicate active-turn behavior.

### Gate

If successful:
- record exact Codex/Desktop versions and behavior;
- continue.

If unsuccessful:
- stop and update architecture;
- do not manipulate rollout/state files manually.

## Phase 2 — AppServerClient

Implement a reusable asynchronous local client.

Suggested file:

```text
codex_bridge/app_server.py
```

### Process lifecycle

Use:

```python
asyncio.create_subprocess_exec(
    codex_command,
    "app-server",
    stdin=PIPE,
    stdout=PIPE,
    stderr=PIPE,
)
```

Do not use `shell=True`.

### Protocol responsibilities

- one long-lived child process;
- initialize exactly once per process;
- newline-delimited JSON writes/reads;
- request ID generation;
- pending request futures;
- server notifications;
- server-initiated requests;
- bounded timeouts;
- safe shutdown;
- process-exit detection.

### Initialization

Send client metadata such as:

```json
{
  "method": "initialize",
  "id": 1,
  "params": {
    "clientInfo": {
      "name": "codex_remote_bridge",
      "title": "Codex Remote Bridge",
      "version": "0.1.0"
    }
  }
}
```

Do not set `experimentalApi`.

Then send:

```json
{"method":"initialized","params":{}}
```

Use actual installed schema if fields differ.

### Request wrappers

Implement only explicit wrappers required by V1:

- thread list;
- thread read;
- thread resume;
- turn start;
- turn interrupt.

Do not expose a generic public `call(method, params)` to the chat router. An internal/private generic transport method is fine.

## Phase 3 — Server notifications and approvals

Build a reader loop that classifies messages:

- response with `id`;
- notification without `id`;
- server-initiated request requiring a client response.

### Turn events

Track by:

- thread ID;
- turn ID.

Collect only necessary user-facing assistant text.

Prefer completed agent-message items or safely accumulated deltas.

On `turn/completed`, resolve the bridge turn future with:

```python
TurnResult(
    thread_id,
    turn_id,
    status,
    final_text,
)
```

### Approval handling

For every approval-style server request:

- never accept;
- choose documented decline/cancel;
- resolve promptly;
- raise/emit a safe `RemoteApprovalRequired` event to router;
- do not log raw sensitive payload.

Add unit tests for every approval request shape that the installed stable schema can emit.

## Phase 4 — Configuration

Suggested:

```text
codex_bridge/config.py
```

Support local environment and optional repository-local `.env`.

Precedence:

```text
OS environment > local .env > safe defaults
```

Required:

- DingTalk client credentials;
- at least one allowed DingTalk user ID;
- at least one allowed Codex root.

Validate at startup before opening the Stream connection.

Normalize CSV/list environment values carefully.

Do not echo secrets on validation errors.

## Phase 5 — Allowed-root and thread filtering

Build path authorization as a dedicated tested component.

Suggested:

```python
is_path_allowed(candidate_cwd, configured_roots) -> bool
```

Requirements:

- native Windows/macOS behavior;
- test Windows paths on non-Windows using pure path helpers where needed;
- canonicalize real runtime paths;
- no relative cwd;
- no traversal;
- descendant check must be path-aware, not string-prefix based.

Example bad check:

```python
candidate.startswith(root)
```

because `D:\work2` should not match `D:\work`.

### Thread listing

Call app-server thread listing, then:

- keep only allowed-root threads;
- sanitize display name/preview;
- return up to configured count;
- never return full cwd to the channel layer.

## Phase 6 — SQLite state

Suggested:

```text
codex_bridge/state.py
```

Initialize with safe migrations/create-if-not-exists.

Tables:

```sql
CREATE TABLE bindings (
  channel TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (channel, conversation_id)
);

CREATE TABLE seen_messages (
  channel TEXT NOT NULL,
  message_id TEXT NOT NULL,
  seen_at INTEGER NOT NULL,
  PRIMARY KEY (channel, message_id)
);
```

Optionally store a short-lived thread list snapshot:

```text
conversation_id -> ordered thread IDs + expiry
```

This may be in memory if stale-index behavior is safely handled; durable storage is not required for the snapshot.

### Dedupe transaction

Ensure message reservation/check is atomic enough that concurrent duplicate callbacks cannot both execute.

Implement cleanup by age/row cap.

## Phase 7 — Core router

Suggested:

```text
codex_bridge/router.py
```

Inputs:

- normalized inbound message;
- channel output interface;
- app-server client;
- state store;
- config.

Router order:

1. authorize;
2. dedupe;
3. normalize/validate text;
4. command dispatch;
5. ordinary-turn dispatch.

Keep provider-specific details out.

### Thread locks

Maintain:

```python
dict[thread_id, asyncio.Lock]
```

and active bridge-owned turn records.

Do not queue an arbitrary backlog.

## Phase 8 — DingTalk adapter

Use official `dingtalk-stream` Python SDK.

Suggested:

```text
channels/dingtalk.py
```

Responsibilities:

- construct Stream credential/client;
- register chatbot callback handler;
- normalize text messages;
- expose stable sender/conversation/message IDs;
- send text replies;
- reconnect according to SDK behavior;
- acknowledge callbacks correctly;
- no Codex logic.

### V1 message types

Accept:
- text.

Ignore/reject:
- images;
- files;
- voice;
- cards as user input;
- unsupported message types.

### 1:1 first

Prefer direct/private bot conversations for acceptance.

If the SDK event model identifies group conversations, enforce disabled-by-default policy.

## Phase 9 — Bridge entry point

Suggested:

```text
bridge.py
```

Startup:

1. load config;
2. initialize state;
3. start app-server client;
4. initialize router;
5. start DingTalk Stream client;
6. run until termination.

Shutdown:

1. stop accepting new messages;
2. stop Stream client;
3. interrupt/leave active work according to explicit policy;
4. close app-server;
5. close state.

Handle Ctrl+C/SIGTERM cleanly on Windows/macOS as practical.

## Phase 10 — User-visible result formatting

Implement one formatter module/function.

Required responses:

- unauthorized/denied;
- help;
- thread list;
- bound/current/unbound;
- started;
- busy;
- completed;
- interrupted;
- approval-required-local;
- safe error.

Default output max:

```text
3000 characters
```

Sanitize full absolute paths from returned final text where practical.

Do not send raw command/tool logs.

## Phase 11 — Offline tests

No secrets/network/real Codex.

### Fake app-server

Create a fake subprocess/protocol fixture capable of:

- initialize response;
- interleaved notifications;
- thread list/read/resume;
- turn start/completed;
- approval server request;
- process death;
- malformed protocol.

### Fake channel

Collect outbound replies and inject normalized inbound messages.

### Test matrix

At minimum:

1. startup config validation;
2. sender authorization;
3. conversation authorization;
4. allowed/disallowed roots;
5. Windows/POSIX path filtering;
6. `/threads`;
7. thread list snapshot expiry;
8. `/use`;
9. stale thread rejection;
10. `/current`;
11. `/unbind`;
12. ordinary text no binding;
13. ordinary text starts exactly one turn;
14. duplicate platform event starts zero extra turns;
15. busy-thread rejection;
16. bridge-owned `/stop`;
17. foreign-active-turn cannot be stopped;
18. approval request always declined;
19. app-server crash;
20. DingTalk adapter normalization;
21. oversized input;
22. Unicode;
23. output truncation;
24. logs do not expose secrets/full text;
25. SQLite restart persistence.

## Phase 12 — CI

Public GitHub Actions:

```text
windows-latest x Python 3.10/current
macos-latest   x Python 3.10/current
```

Run:

- unittest/pytest chosen by implementation;
- compile checks;
- lint if a lightweight tool is intentionally added;
- `git diff --check`.

No secret-dependent integration test in public CI.

## Phase 13 — Real DingTalk smoke test

Use a dedicated bot/app and safe repository.

Validate:

```text
DingTalk direct message
  -> Stream callback
  -> authorized router
  -> bot echo/help
```

Before connecting to Codex, test:

- `/help`;
- unauthorized sender;
- duplicate message behavior if reproducible.

## Phase 14 — End-to-end test

On Windows first:

1. finish a harmless Desktop Codex turn;
2. start bridge;
3. DingTalk `/threads`;
4. ensure only allowed project appears;
5. `/use 1`;
6. send harmless follow-up;
7. verify exactly one Codex turn starts;
8. verify local file/context behavior;
9. verify final answer arrives in DingTalk;
10. test `/stop` on a bridge-started long turn;
11. trigger a task requiring forbidden elevation and verify it is not approved remotely.

Repeat core path on macOS.

## Phase 15 — Documentation after implementation

README must be updated with:

- DingTalk app creation/configuration;
- where to obtain client ID/secret;
- how to identify allowed user IDs safely;
- direct-chat setup;
- Python/install commands;
- `codex` path discovery;
- `.env` setup;
- allowed roots;
- run command;
- startup/manual background options;
- troubleshooting;
- security warnings;
- validation status.

`docs/VALIDATION.md` must distinguish:

- automated tests;
- CI;
- real Windows;
- real macOS;
- real DingTalk;
- Desktop-thread handoff.

## Definition of Done

V1 is complete only when:

- go/no-go handoff passes or scope is formally changed;
- implementation and tests exist;
- Windows/macOS CI passes;
- DingTalk direct-message flow works;
- allowlists work;
- allowed-root filtering works;
- existing allowed Codex thread can receive a remote follow-up;
- final response returns to DingTalk;
- duplicate event does not duplicate work;
- no remote approval succeeds;
- no public app-server port exists;
- no real credential is committed;
- limitations are documented.
