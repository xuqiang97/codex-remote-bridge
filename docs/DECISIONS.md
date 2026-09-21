# Architecture and Product Decisions

## Decision 028 — Persistent DingTalk task coordinator

Owner-approved on 2026-09-21. Normal chat must not require manually binding a target.
Create one persistent coordinator per private conversation. Use stable structured
turn output and explicitly validated host operations instead of experimental dynamic
tools or app-specific in-memory tool APIs. This works against each installation's
own Codex/user/home, without shipping this developer's credentials or paths.

The coordinator may read allowed metadata/recent final answers and request an
explicitly authorized target turn. Python checks the target and exact current-user
instruction. DingTalk completion uses the official proactive private message API,
which avoids session webhook expiry. Restart does not replay work or assume turn
ownership. Failed/uncertain sends are recorded; automatic reconciliation is pending.


This document records settled V1 decisions for `codex-remote-bridge`.

Future contributors may change them only with new evidence and corresponding documentation updates.

## Decision 026 — Existing threads remain the product; writer conflicts fail closed

**Status:** Accepted, 2026-09-21 owner clarification and successful continuity probe.

The product must continue existing Desktop tasks for independent Windows users.
Do not replace this with bridge-created-only tasks. The previous No-Go was real
for a Desktop-loaded idle thread. The same test thread later became available
and passed `thread/resume` plus `turn/start` with conversation-only recall.
The action that released Desktop ownership was not established.

Preserve the independent local stdio app-server architecture. List all eligible
tasks with bounded pagination (`/threads [page]`). A list/read status of
`notLoaded` is not cross-client ownership proof. `thread/resume` must succeed
under the server's writer exclusion before starting a turn; reject ownership
errors without retry, force-unlock, UI automation or hidden-state access.
Loaded Desktop tasks may remain unavailable even after their turn completes.
This is a documented product limitation, not universal task availability.

The bridge keeps one local app-server process. It can hold a resumed thread's
writer until shutdown; stop the bridge before returning to that thread in
Desktop if Desktop reports an ownership conflict. `/unbind` only removes the
chat mapping. It does not unload, archive, interrupt or delete the thread.

## Decision 027 — Portable, per-user configuration

Each installation uses its own native Codex executable, OS user, Codex home,
DingTalk bot identity, user allowlist and JSON-array project-root allowlist.
No real values are part of the repository or release. No centralized service,
shared developer bot or machine-specific paths are required. Remote SSH/cloud
tasks visible in Desktop are not local threads supported by this release.

## Decision 001 — Separate project from codex-notify

**Status:** Accepted

`codex-notify` stays focused on one-way completion notifications.

`codex-remote-bridge` is a separate repository because two-way remote control introduces:

- identity and authorization;
- thread selection/binding;
- persistent state;
- concurrency;
- app-server lifecycle;
- approvals/permission handling;
- chat-provider inbound events;
- significantly higher security risk.

This separation keeps both projects understandable.

## Decision 002 — Python

**Status:** Accepted

Use Python 3.10+.

Reasons:

- current maintainers already have Python on Windows/macOS;
- `codex-notify` already uses Python;
- official DingTalk Stream SDK provides Python support;
- asyncio/subprocess/JSON/SQLite are sufficient;
- cross-platform.

## Decision 003 — Codex app-server, not UI automation

**Status:** Accepted

Use the official `codex app-server` protocol.

Do not automate:

- ChatGPT/Codex Desktop UI;
- keyboard/mouse;
- remote desktop;
- local rollout files directly.

Official app-server exposes stored thread and turn APIs including `thread/list`, `thread/read`, `thread/resume`, `turn/start`, and `turn/interrupt`.

Reference:
- https://developers.openai.com/docs/app-server

## Decision 004 — stdio app-server transport

**Status:** Accepted

Spawn `codex app-server` as a local child process and communicate over stdio.

Do not expose a TCP/WebSocket app-server listener.

Reasons:

- smallest attack surface;
- no inbound port;
- no local firewall/public binding mistakes;
- lifecycle naturally belongs to the bridge process.

## Decision 005 — Stable app-server APIs only

**Status:** Accepted

Do not opt into `experimentalApi` for V1.

Reasons:

- remote-control software should minimize unstable surface;
- stable thread/turn APIs are sufficient for the initial goal;
- experimental permission/tool functionality would expand risk.

## Decision 006 — Existing-thread continuation is the V1 value proposition

**Status:** Accepted with validation gate

The desired user experience is to continue an already completed local Desktop Codex conversation.

However, the official docs describe stored-thread resume, not a guarantee for every cross-client/Desktop ownership scenario.

Therefore same-machine Desktop-thread -> app-server resume is a hard pre-implementation validation.

If unsupported/unreliable, V1 must be re-scoped honestly.

## Decision 007 — DingTalk first

**Status:** Accepted

V1 implements DingTalk before Feishu.

Reasons:

- immediate user workflow relevance;
- official DingTalk Stream Mode Python SDK exists;
- Stream Mode uses an outbound long connection and avoids a public webhook server;
- chatbot message receiving fits the local-first architecture.

Official SDK:
- https://github.com/open-dingtalk/dingtalk-stream-sdk-python

Feishu remains a future channel adapter.

## Decision 008 — Stream Mode, not public webhook

**Status:** Accepted

The local computer connects outward to DingTalk.

Do not host a public callback server for V1.

This preserves:

```text
Internet -> no open port on local machine
local machine -> DingTalk Stream
```

## Decision 009 — Channel adapter boundary

**Status:** Accepted

Core bridge logic sees normalized messages, not DingTalk SDK objects.

V1 implements only DingTalk, but a future Feishu adapter should not require rewriting Codex routing.

Keep this boundary light; do not build a generic plugin framework.

## Decision 010 — Explicit allowlists

**Status:** Accepted

Remote-control access uses stable DingTalk IDs with default-deny behavior.

Required:

- user allowlist;
- project-root allowlist.

Conversation allowlist is recommended and becomes mandatory for group-chat support.

Display names are never authorization.

## Decision 011 — Private/direct chat preferred

**Status:** Accepted

V1 should be validated in a direct/private bot conversation.

Group chat remote control is off by default because:

- larger audience;
- accidental commands;
- identity/mention ambiguity;
- higher risk of exposing project metadata.

Explicit group support can be added later with sender + conversation allowlists.

## Decision 012 — Explicit thread binding

**Status:** Accepted

No “latest thread executes automatically” behavior.

The user must:

```text
/threads
/use <index>
```

Then ordinary messages target the selected thread.

Reasons:

- prevents wrong-repository actions;
- transparent mental model;
- easier auditing/debugging;
- safer when multiple Codex projects exist.

## Decision 013 — Allowed project roots are mandatory

**Status:** Accepted

Remote thread listing must be filtered to configured local roots.

Do not expose every thread stored under the user's Codex home.

The chat cannot provide a path.

## Decision 014 — Conservative remote execution

**Status:** Accepted

Target V1 policy:

```text
approvalPolicy=never
sandbox=workspaceWrite
```

No remote full-access mode.

The exact request shape must match the installed Codex app-server schema; generate/read the local schema if necessary.

The policy intent is more important than string literals if Codex naming changes.

## Decision 015 — No remote approval

**Status:** Accepted

The app-server can request command/file/permission approvals from its client.

V1 never accepts them remotely.

Reasons:

- chat account compromise would otherwise become privilege escalation;
- approval UI must show enough context to make an informed decision;
- remote approval requires a stronger threat model and audit design.

If approval is required, decline/cancel and tell the user local attention is needed.

## Decision 016 — No generic RPC passthrough

**Status:** Accepted

Never implement:

```text
/rpc <method> <json>
```

Only explicit, reviewed bridge operations are callable.

Methods such as `thread/shellCommand` and `command/exec` are prohibited.

## Decision 017 — No automatic turn steering in V1

**Status:** Accepted

Although app-server supports `turn/steer`, ordinary messages to a busy thread should be rejected in V1.

Reasons:

- simpler semantics;
- avoids accidental mid-turn instruction changes;
- easier ownership/concurrency model.

A future explicit `/steer` command may be considered.

## Decision 018 — Bridge-owned stop only

**Status:** Accepted

`/stop` can interrupt only a turn the bridge itself started and currently tracks.

Do not interrupt a turn merely because the thread appears active.

This protects concurrent Desktop use.

## Decision 019 — SQLite local state

**Status:** Accepted

Use Python standard-library `sqlite3` for durable:

- conversation -> thread binding;
- inbound message dedupe.

Reasons:

- no external service;
- cross-platform;
- atomic enough for dedupe/binding;
- survives restart;
- no third-party dependency.

Do not store conversational content/secrets.

## Decision 020 — One active turn per thread

**Status:** Accepted

No queue in V1.

If the selected thread is busy, respond with busy state.

This is easier to reason about and prevents duplicate/concurrent edits.

## Decision 021 — DingTalk official SDK is an acceptable dependency

**Status:** Accepted

Unlike `codex-notify`, zero third-party dependencies are not a goal here.

The official Stream SDK solves authentication/reconnect/message handling appropriately.

Keep other direct dependencies minimal.

## Decision 022 — Final response, not token streaming

**Status:** Accepted

V1 should acknowledge start, then return a concise final response.

Do not stream every assistant delta to DingTalk.

Reasons:

- avoids message flood;
- simplifies retries/dedupe;
- easier mobile UX;
- reduces accidental exposure.

Rich streaming cards can be future work.

## Decision 023 — Single bridge host per bot identity

**Status:** Accepted

V1 does not solve multi-computer routing.

Do not run the same bot/app identity across multiple computers and assume deterministic delivery/fan-out.

Use one designated host or separate credentials per host for V1.

Multi-device routing belongs in V2.

## Decision 024 — No tight integration with codex-notify in V1

**Status:** Accepted

Both tools can coexist independently.

Later, `codex-notify` may hand off a completed `thread-id` locally to improve binding UX, but V1 should first prove remote bridge fundamentals without cross-repository coupling.

## Decision 025 — Real validation before feature expansion

**Status:** Accepted

Before adding Feishu/cards/steering/multi-device features, validate:

```text
DingTalk -> bridge -> existing Codex thread -> new turn -> DingTalk
```

on a safe test repository on Windows and macOS.
