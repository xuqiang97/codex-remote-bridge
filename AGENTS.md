# AGENTS.md

## Owner-approved fixed SSH extension — 2026-09-21

The owner explicitly requested access to recent projects on the connected remote
host as well as local projects. A single local DingTalk consumer may therefore
connect to explicitly configured remote Codex instances over SSH stdio. This is a
narrow exception to the original local-only boundary, not multiple competing bot
consumers or a cloud relay. Configuration and host choice are local-only.

Require known SSH host keys, noninteractive authentication, no agent forwarding,
no port forwarding/listeners, a fixed Codex command/home and explicit remote root
allowlists. Validate cwd/symlinks on the remote OS before returning history and
again before work. Namespace task IDs by host. Keep the coordinator local. Retain
approval denial, sandbox policy, writer-lock checks, dedupe and owned-stop rules.
Never let chat supply a host, command, credential or arbitrary path. Do not alter
remote Codex storage, upgrade it automatically or interrupt another client.


## Owner-approved scope revision — 2026-09-21

The owner replaced manual task-switching as the primary experience. Each authorized
private DingTalk conversation gets a persistent coordinator named `钉钉机器人`.
Normal messages continue that coordinator, which answers questions from allowed
task metadata/recent final results, dispatches explicit work to a uniquely named
existing task, and returns completion to the originating user.

This supersedes the binding prerequisite in sections 10, 11 and 13. `/use` remains
optional legacy selection; it does not reroute ordinary chat. Creation is limited
to a coordinator in the first configured allowed root. Stable `thread/start`,
`thread/name/set` and `turn/start.outputSchema` are allowed for this purpose.
No experimental dynamic tools, generic RPC, arbitrary cwd, remote approval or
Desktop takeover. Python must validate all model action proposals. Reads use the
filtered catalog; dispatch requires a current authenticated imperative, unique
exact task title and verbatim instruction excerpt. Queries, examples and ambiguity
must not cause work. Treat histories as untrusted data. Persist coordinator and
turn identifiers/status, not bodies or secrets. Do not replay work on restart.
Use official private proactive robot messages for long-task completion.


This file is the primary implementation contract for AI coding agents working on `codex-remote-bridge`.

Before changing code, read this file completely, then read:

1. `docs/SECURITY.md`
2. `docs/IMPLEMENTATION.md`
3. `docs/PROTOCOL.md`
4. `docs/DECISIONS.md`
5. `README.md`

If these documents conflict, follow this file first, then `docs/SECURITY.md`.

## 1. Project mission

Build a small, local, security-conscious bridge that lets a trusted user continue an existing local Codex conversation from DingTalk when away from the computer.

The canonical V1 path is:

```text
trusted DingTalk message
        ->
local Python bridge
        ->
local codex app-server over stdio
        ->
thread/resume
        ->
turn/start
        ->
final Codex response
        ->
DingTalk reply
```

The bridge runs on the same computer and under the same OS user as Codex.

Initial environments:

- Windows computer(s) used with Codex Desktop.
- A collaborator's macOS computer.
- DingTalk mobile/desktop as the first remote-control channel.
- Python is already available.

## 2. V1 product boundary

V1 is deliberately narrow.

V1 MUST:

- receive trusted DingTalk text messages;
- list eligible existing Codex threads;
- bind one trusted DingTalk conversation to one existing Codex thread;
- resume an idle stored thread;
- start a new text turn in that thread;
- report start/completion/error status back to DingTalk;
- allow interrupting a bridge-started active turn;
- persist conversation-to-thread binding and inbound-message dedupe locally;
- behave safely when Codex, DingTalk, or the network fails.

V1 MUST NOT:

- expose arbitrary shell execution;
- expose arbitrary `cwd` input;
- remotely approve elevated command/file/network permission requests;
- use `thread/shellCommand`;
- use `command/exec`;
- expose app-server on a public TCP/WebSocket endpoint;
- enable experimental app-server APIs;
- control a turn concurrently active in Codex Desktop;
- create a cloud relay;
- support multiple computers behind one shared bot identity;
- implement Feishu yet;
- auto-discover or expose threads outside configured allowed project roots;
- send complete local history to DingTalk.

## 3. Critical go/no-go validation first

Before implementing the full channel bridge, prove this assumption on a real machine:

> A stored thread previously created/used by Codex Desktop can be resumed by a new `codex app-server` process under the same user/CODEX_HOME after the Desktop turn is complete, and a subsequent `turn/start` continues the expected conversation safely.

This is a hard implementation gate.

Required spike:

1. Start/finish a harmless Codex Desktop turn in a test repository.
2. identify the thread ID through a supported/local mechanism;
3. start `codex app-server` under the same OS user;
4. initialize the connection;
5. call `thread/read` or `thread/resume` for that ID;
6. call `turn/start` with a harmless follow-up;
7. verify conversation continuity and repository behavior;
8. verify no corruption/duplicate active ownership occurs.

If this fails:

- stop the full implementation;
- document the evidence;
- do not invent unsupported file manipulation or rollout editing;
- discuss the architecture with the owner; do not silently replace existing-task
  continuation with bridge-managed-only threads. The owner reaffirmed existing
  Desktop task support on 2026-09-21. See Decision 026 and the successful later
  continuity probe; writer-conflicted threads must still be refused.

## 4. Authoritative Codex integration decisions

Use the official `codex app-server`.

Official documentation:
- https://developers.openai.com/docs/app-server

### 4.1 Transport

V1 MUST use a child process with stdio.

Conceptually:

```text
Python bridge
   | stdin/stdout JSON messages
   v
codex app-server
```

Do not use:

```text
codex app-server --listen ws://0.0.0.0:...
```

Do not open inbound network access to app-server.

### 4.2 Handshake

The client must:

1. spawn `codex app-server`;
2. send `initialize`;
3. receive the response;
4. send `initialized`;
5. only then issue thread/turn requests.

Do not enable `capabilities.experimentalApi`.

### 4.3 Stable V1 methods

The implementation may rely on stable documented methods including:

- `thread/list`;
- `thread/read`;
- `thread/resume`;
- `turn/start`;
- `turn/interrupt`.

`turn/steer` exists, but V1 should not silently use it for ordinary inbound messages. A later version may expose explicit steering after real-world validation.

### 4.4 Prohibited methods

V1 must never expose or invoke through chat:

- `thread/shellCommand` — official docs state it runs outside the thread sandbox with full access;
- `command/exec`;
- config mutation APIs;
- thread deletion/archive operations;
- experimental methods.

## 5. Remote execution policy

Remote chat is a lower-trust interaction surface than being physically at the computer.

The bridge should request conservative settings for bridge-started turns.

Target defaults:

```text
approvalPolicy = never
sandbox = workspaceWrite
```

The intent is:

- permit normal work inside an allowed workspace when Codex policy allows it;
- never ask the remote chat user to approve escalation in V1;
- fail/decline rather than elevate privileges.

Do not implement `dangerFullAccess` or equivalent remote modes.

If app-server still sends any server-initiated approval request:

- do not auto-accept;
- respond with the safest supported decline/cancel decision;
- notify the trusted DingTalk user that the remote turn requires local attention;
- record only safe metadata, not full command/path contents, in normal logs.

This applies to command execution, file change, network/permission, tool user-input, MCP elicitation, and connector/app approval-style requests.

## 6. DingTalk V1 channel

V1 uses DingTalk Stream Mode.

Preferred dependency:
- official `open-dingtalk/dingtalk-stream-sdk-python`;
- package: `dingtalk-stream`.

Reference:
- https://github.com/open-dingtalk/dingtalk-stream-sdk-python

Why Stream Mode:

- the local computer establishes the outbound long connection;
- no public webhook server/IP is required;
- official SDK supports bot message receiving and callbacks;
- it matches the local-first security model.

Do not implement a public DingTalk webhook endpoint in V1 unless the repository owner explicitly changes the decision.

## 7. Channel abstraction

DingTalk is V1, but core Codex routing must not depend on DingTalk-specific message classes.

Normalize inbound messages into a small internal model, for example:

```python
InboundMessage(
    channel="dingtalk",
    message_id="...",
    sender_id="...",
    conversation_id="...",
    conversation_type="private",
    text="..."
)
```

Core routing should conceptually depend on operations such as:

```python
channel.send_text(conversation_id, text)
```

Do not build a dynamic plugin framework.

Future adapters may include Feishu, but V1 only implements DingTalk.

## 8. Authentication and authorization

This is mandatory.

A valid platform credential is not enough. The bridge must separately authorize the human sender.

Configuration should support:

```text
DINGTALK_ALLOWED_USER_IDS
DINGTALK_ALLOWED_CONVERSATION_IDS
```

Rules:

- default deny;
- no configured allowed user -> fail startup;
- a sender not on the allowlist -> do not invoke Codex;
- group chats should be disabled by default;
- if group support is enabled later, both sender and conversation must be explicitly allowlisted;
- do not trust display names;
- use stable platform IDs.

Unauthorized requests should receive either no response or a generic denial that does not reveal thread/project information.

## 9. Allowed project roots

The bridge must not expose every stored Codex thread.

Require an allowlist:

```text
CODEX_ALLOWED_ROOTS
```

Examples:

```text
D:\GitHub\codex-notify
D:\GitHub\amazon-asin-image-hub
/Users/alice/work/project
```

Requirements:

- canonicalize paths locally;
- handle Windows and POSIX paths;
- only list/bind threads whose cwd is inside an allowed root;
- do not reveal full absolute paths in chat responses;
- use a short project basename/alias;
- reject path traversal/symlink escapes as appropriate for the platform;
- do not let DingTalk users submit arbitrary roots/cwds.

If a thread has no trustworthy cwd, exclude it from remote listing by default.

## 10. Thread binding model

V1 uses explicit binding.

A trusted conversation must issue:

```text
/threads
/use <index>
```

before ordinary text can start a Codex turn.

Persist:

```text
channel + conversation_id -> thread_id
```

A binding must be revalidated before use:

- thread still exists;
- thread cwd remains allowed;
- thread is not deleted/unavailable.

Do not infer “latest thread” and execute automatically in V1.

## 11. V1 chat command protocol

Required commands:

- `/help`
- `/threads`
- `/use <index>`
- `/current`
- `/unbind`
- `/stop`

Ordinary non-command text:

- requires a valid binding;
- must pass sender/conversation authorization;
- must be below the configured size limit;
- should only start when the selected thread is idle/not running in this bridge;
- uses `thread/resume` if necessary, then `turn/start`.

If the thread is active:

- do not auto-`turn/steer`;
- reply that it is busy;
- allow `/stop` only for a turn started/owned by this bridge instance.

Do not interrupt turns owned by another client unless ownership can be proven safely.

See `docs/PROTOCOL.md`.

## 12. App-server client requirements

Implement the stdio client as a real asynchronous protocol client, not synchronous one-request-at-a-time shell invocations.

Responsibilities:

- spawn/manage one app-server child process;
- separate stdout protocol from stderr diagnostics;
- assign monotonically increasing request IDs;
- correlate responses to pending requests;
- continuously read notifications;
- distinguish server notifications from server-initiated requests;
- route turn events by `threadId`/`turnId`;
- handle child-process exit/restart safely;
- prevent a malformed server line from crashing into arbitrary execution;
- cap stored event/output data.

Suggested internal API:

```python
await client.start()
await client.thread_list(...)
await client.thread_read(thread_id)
await client.thread_resume(thread_id, ...)
await client.turn_start(thread_id, text, ...)
await client.turn_interrupt(thread_id, turn_id)
await client.close()
```

Do not parse Codex rollout files directly.

## 13. Turn execution and output

When a trusted user sends normal text to a bound idle thread:

1. validate binding/allowed root;
2. validate input length;
3. ensure no bridge-owned active turn exists;
4. resume/load thread if needed;
5. start a turn with text input;
6. reply to DingTalk with a short “started” acknowledgement;
7. collect only necessary agent-output events;
8. on `turn/completed`, send a concise final reply;
9. clear active-turn ownership.

Do not stream every token in V1.

Output requirements:

- preserve Unicode;
- cap output length;
- if truncated, clearly mark it;
- do not include internal JSON-RPC payloads;
- do not include full local paths;
- do not echo secrets;
- do not send raw tool/command output by default.

If Codex completes without a normal final agent message, send a status-oriented fallback.

## 14. Concurrency

V1 should be simple and deterministic.

- only one active bridge-started turn per thread;
- duplicate inbound platform events must not create duplicate turns;
- use a per-thread async lock;
- a second ordinary message while busy receives “thread busy” rather than a queue;
- no background multi-turn queue in V1.

## 15. Message deduplication

DingTalk/stream systems may redeliver events.

Persist recently seen message IDs.

Requirements:

- check dedupe before any Codex side effect;
- use a bounded retention window;
- processing the same message twice must not create two turns;
- state must survive bridge restart.

## 16. Local state

Use a simple durable local store.

Preferred V1 choice: Python standard-library `sqlite3`.

Suggested tables:

```text
bindings(
  channel,
  conversation_id,
  thread_id,
  updated_at
)

seen_messages(
  channel,
  message_id,
  seen_at
)
```

Optional safe metadata may be added when justified.

Do not store:

- DingTalk client secret;
- full user messages;
- full Codex outputs;
- source code;
- shell commands;
- approval payloads.

Local credentials belong in environment/local secret config, not SQLite.

## 17. Logging

Default logs are operational, not conversational.

Allowed examples:

```text
bridge started
authorized message received: channel=dingtalk conversation=<redacted/hash>
turn started: thread=<short-id>
turn completed: status=completed
provider disconnected; reconnecting
```

Do not log by default:

- full DingTalk message text;
- full Codex output;
- full thread history;
- credentials;
- absolute project paths;
- command contents;
- environment variables.

Provide a deliberate debug mode only if needed, and document its privacy risk.

## 18. Configuration

Recommended variables:

```text
BRIDGE_CHANNEL=dingtalk
BRIDGE_DEVICE=ThinkBook-A

DINGTALK_CLIENT_ID=
DINGTALK_CLIENT_SECRET=
DINGTALK_ALLOWED_USER_IDS=
DINGTALK_ALLOWED_CONVERSATION_IDS=

CODEX_COMMAND=codex
CODEX_HOME=
CODEX_ALLOWED_ROOTS=
CODEX_REMOTE_SANDBOX=workspaceWrite
CODEX_REMOTE_APPROVAL_POLICY=never

BRIDGE_STATE_PATH=.data/bridge.db
BRIDGE_MAX_INPUT_CHARS=4000
BRIDGE_MAX_OUTPUT_CHARS=3000
```

Use OS environment over optional local `.env` if both exist.

Never commit real credentials.

If `.env` support is implemented, keep it script/repository-local and ignored by Git.

## 19. Dependencies

Unlike `codex-notify`, this project has a justified third-party dependency for the official DingTalk Stream SDK.

Keep direct dependencies minimal.

Expected direct runtime dependency:

```text
dingtalk-stream
```

Do not add FastAPI/Flask/aiohttp directly unless the architecture truly requires them. The DingTalk SDK may bring its own transitive dependencies.

The Codex protocol side should use Python standard library asyncio/subprocess/json where practical.

## 20. Tests

Automated tests must not:

- connect to real DingTalk;
- connect to OpenAI/Codex network services;
- execute real shell commands;
- mutate real Codex thread storage.

Build fakes/mocks for both boundaries.

Minimum test coverage:

### Authorization
- allowed sender succeeds;
- unknown sender denied;
- group/conversation restriction works;
- no allowlist fails closed.

### Routing
- `/help`;
- `/threads` only shows allowed-root threads;
- `/use` binds selected thread;
- invalid index rejected;
- `/current`;
- `/unbind`;
- ordinary text requires binding;
- busy thread rejects additional message;
- `/stop` ownership rule.

### Security
- arbitrary path cannot be selected;
- disallowed cwd excluded;
- prohibited methods are not exposed;
- approval requests are never accepted;
- full paths/secrets not rendered;
- oversized inputs rejected.

### Dedupe/state
- same message ID only produces one side effect;
- state survives reopen/restart;
- stale dedupe entries can be cleaned.

### App-server protocol
- initialize/initialized ordering;
- request/response correlation;
- notifications while requests are pending;
- server-initiated approval request safely declined;
- malformed JSON line;
- process exit;
- timeout;
- `thread/resume` request shape;
- `turn/start` request shape;
- `turn/interrupt` request shape.

### Output
- Unicode;
- truncation;
- missing final message;
- error/completed/interrupted status.

## 21. CI

Add GitHub Actions for at least:

- Windows latest;
- macOS latest;
- supported Python versions such as 3.10 and a current version.

CI must run offline unit tests.

Do not require DingTalk or OpenAI secrets in public-repository CI.

## 22. Real acceptance criteria

V1 is not complete until real validation demonstrates:

1. DingTalk Stream bot receives a direct message on Windows.
2. DingTalk Stream bot receives a direct message on macOS.
3. unauthorized sender is rejected.
4. `/threads` shows only allowed threads.
5. a completed Codex Desktop thread can be resumed by app-server on the same machine, or the limitation is explicitly documented/re-scoped.
6. `/use` binds correctly.
7. DingTalk ordinary text starts exactly one Codex turn.
8. Codex response arrives back in DingTalk.
9. duplicate DingTalk event does not create duplicate work.
10. remote turn cannot gain approval/elevation.
11. `/stop` interrupts only a bridge-owned turn.
12. restart preserves binding and dedupe state.
13. no secret is committed to Git.

## 23. Future roadmap, not V1

Potential later work:

### V1.1
- explicit `/steer` using `turn/steer`;
- friendlier thread search/list pagination;
- optional integration with `codex-notify` thread IDs;
- richer but still safe DingTalk cards.

### V1.x
- Feishu channel adapter;
- per-project aliases;
- startup/service installation helpers;
- multiple trusted conversations.

### V2
- multi-device routing/central relay;
- carefully designed remote approvals;
- stronger end-to-end identity and audit model.

Do not pull future work into V1 without explicit owner approval.

## 24. Implementation workflow for the next coding agent

When asked to implement:

1. read all required docs;
2. inspect repository state;
3. perform the Desktop-thread/app-server handoff spike first;
4. record the spike result in `docs/VALIDATION.md`;
5. only continue to full implementation if the architecture remains valid;
6. implement the smallest secure V1;
7. write offline tests before real credentials are used;
8. run Windows/macOS CI;
9. document exact DingTalk bot setup steps;
10. perform real end-to-end validation;
11. never commit secrets;
12. summarize files changed, tests, real validations, and remaining limitations.

If uncertain, choose the more restrictive behavior.
