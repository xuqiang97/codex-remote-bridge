# V1 Chat Protocol

## Coordinator protocol revision — 2026-09-21

This supersedes ordinary-message binding rules below. First private chat creates
`钉钉机器人`; later messages continue that same Codex task. Examples:
`今天主要有哪些任务？`, `某某任务刚刚的结果是什么？`,
`请在「完整任务名」任务中执行：检查测试并报告结果。`
Only allowed projects are visible. Recent results are bounded, not a complete daily
activity ledger. Ambiguous titles and unsupported instructions ask for clarification.
Questions never authorize target work.

`/threads` is diagnostic; `/use` and `/unbind` affect legacy selection only, never
ordinary chat routing. `/current` identifies the coordinator. `/stop` interrupts
only this conversation's unique bridge-owned turn; no candidates or multiple
candidates are rejected. Desktop-owned turns cannot be controlled.

A target start acknowledgement follows successful turn/start. Completion sends the
named final answer via proactive private robot API. Delivery uncertainty is recorded
without retrying work. Automatic restart reconciliation is not implemented; this limitation must be disclosed.


This document defines the user-visible command protocol and the normalized internal channel contract.

V1 channel: DingTalk Stream Mode.

## 1. Design principles

- small command surface;
- explicit thread binding;
- no implicit execution across projects;
- no remote approval/elevation;
- no silent steering of an active turn;
- concise, predictable replies.

## 2. Normalized inbound message

Channel adapters should convert provider-specific events into a provider-neutral model.

Suggested fields:

```python
@dataclass(frozen=True)
class InboundMessage:
    channel: str
    message_id: str
    sender_id: str
    conversation_id: str
    conversation_type: str
    text: str
```

Optional provider metadata may exist inside the adapter, but core routing should not depend on DingTalk SDK classes.

## 3. Authorization order

For every inbound message:

1. validate event structure;
2. extract stable sender/conversation/message IDs;
3. verify sender allowlist;
4. verify conversation policy;
5. check dedupe;
6. normalize text;
7. route command or ordinary text.

No Codex interaction happens before steps 1–5 pass.

## 4. Command grammar

Commands are ASCII slash-prefixed and case-insensitive.

Required:

```text
/help
/threads
/current
/use <index>
/unbind
/stop
```

Whitespace around arguments may be normalized.

Unknown commands should return a short help hint and perform no Codex side effect.

## 5. /help

Returns the minimal supported command list.

Example:

```text
Commands:
/threads - list eligible Codex threads
/use <n> - bind this chat to a thread
/current - show current binding/status
/unbind - remove binding
/stop - stop the turn started by this bridge
/help - show help

After /use, send normal text to continue that Codex thread.
```

Do not include local paths or credentials.

## 6. /threads

Purpose: list resumable, allowed Codex threads.

Implementation:

- request threads from app-server;
- filter by `CODEX_ALLOWED_ROOTS`;
- exclude threads with missing/untrusted cwd;
- prefer recent threads;
- cap list size, recommended 10;
- map displayed indices to thread IDs for this response/context.

Display safe metadata only:

- index;
- thread name/preview if safe;
- project basename/alias;
- high-level status.

Example:

```text
Eligible Codex threads:
1. [codex-notify] Review ntfy provider — idle
2. [amazon-asin-image-hub] A+ aggregation update — idle

Use: /use 1
```

Never show full thread IDs unless debug/admin mode explicitly requires it.

Never show full cwd.

### Index semantics

The implementation also accepts `/threads <page>` for browsing the stored list
in pages of ten. Global indices remain stable for five minutes; `/threads`
refreshes the snapshot. Listing is bounded to 100 app-server pages of 100 rows;
an oversized catalogue fails without publishing a partial selectable snapshot.

The implementation must avoid stale-index surprises.

Recommended:

- store a short-lived per-conversation thread-list snapshot;
- `/use 1` resolves against the most recent snapshot;
- expire the snapshot after a bounded time;
- revalidate the selected thread/root before binding.

If no snapshot exists, ask the user to run `/threads` again.

## 7. /use <index>

Binds the trusted DingTalk conversation to one thread from the latest validated `/threads` snapshot.

Before storing binding:

- re-read/revalidate thread;
- verify cwd remains allowed;
- verify thread exists;
- reject unsupported/unsafe status if necessary.

Reply:

```text
Bound to codex-notify.
Send normal text to continue this thread.
```

Binding does not start a Codex turn.

## 8. /current

Shows:

- project alias/basename;
- safe thread display name if available;
- current status: idle/busy/unavailable;
- whether the active turn is owned by this bridge.

Example:

```text
Current: codex-notify
Status: idle
```

Do not show full path or raw RPC status payload.

## 9. /unbind

Deletes the conversation-to-thread binding.

It does not:

- archive/delete the Codex thread;
- interrupt any active turn;
- modify local project data.

Reply:

```text
Binding cleared.
```

## 10. Ordinary text

If message does not start with `/`:

### Preconditions

- sender authorized;
- conversation authorized;
- not duplicate;
- non-empty;
- <= configured max input length;
- valid binding exists;
- thread still exists;
- cwd still allowed;
- no conflicting active turn.

### Execution

1. load/resume thread if needed;
2. apply conservative remote execution settings;
3. call `turn/start` with one text input item;
4. record bridge ownership of returned turn ID;
5. send acknowledgement;
6. await turn events;
7. send final result;
8. clear ownership.

Example acknowledgement:

```text
Started on codex-notify.
```

## 11. Busy-thread behavior

V1 does not queue ordinary messages and does not auto-steer.

If thread is active:

```text
This Codex thread is busy.
Wait for completion or use /stop if this bridge started the current turn.
```

If active ownership is unknown/not bridge-owned:

```text
This thread is active in another client. Remote control is disabled until it becomes idle.
```

## 12. /stop

Purpose: interrupt only the active turn started by this bridge.

Conditions:

- a binding exists;
- active turn ID exists locally;
- ownership belongs to this bridge instance/session.

Then call `turn/interrupt`.

Reply on accepted request:

```text
Stop requested.
```

On no owned active turn:

```text
No bridge-owned active turn to stop.
```

Do not interrupt a turn merely because `thread/read` says the thread is active.

## 13. Turn completion

On `turn/completed`:

- inspect final status;
- use the final assistant-facing message accumulated from agent message events;
- produce a safe/truncated DingTalk response.

Example success:

```text
Completed · codex-notify

Updated README and tests. All offline tests pass.
```

Example interrupted:

```text
Interrupted · codex-notify
```

Example failure:

```text
Codex turn failed · codex-notify
Open the computer for details if needed.
```

Do not dump raw protocol errors to the chat.

## 14. Approval-required behavior

V1 never remotely approves.

If the app-server sends an approval/server request that cannot proceed under the conservative policy:

1. decline/cancel safely;
2. send:

```text
Remote turn needs local approval/access and was not elevated.
Open Codex on the computer to continue safely.
```

No Accept button or `/approve` command exists in V1.

## 15. Duplicate events

If the same platform `message_id` is delivered again:

- do not send a second Codex turn;
- ideally avoid duplicate bot output too;
- acknowledge platform delivery as required by SDK/protocol.

Dedupe must happen before execution.

## 16. Errors

User-facing errors should be actionable and non-sensitive.

Examples:

```text
No thread is bound. Run /threads first.
```

```text
That thread is no longer available. Run /threads again.
```

```text
Codex bridge is temporarily unavailable. No local action was performed.
```

Never include:

- client secret;
- raw exception with URLs/tokens;
- full local path;
- raw command/tool payload;
- full JSON-RPC request/response.

## 17. Output length

Default recommended `BRIDGE_MAX_OUTPUT_CHARS=3000`.

If final text exceeds the limit:

- truncate on a Unicode-safe character boundary;
- append a clear suffix such as:

```text
… [truncated; open Codex locally for full output]
```

Do not split into dozens of messages in V1.

## 18. Future protocol additions

Not V1:

- `/steer <text>`;
- `/new`;
- `/approve`;
- `/shell`;
- `/project <path>`;
- file/image upload;
- rich-card action buttons;
- cross-device routing commands.

Any future command that increases privilege requires a security review first.

## Multiple fixed hosts

Ordinary chat continues the same local coordinator. Task entries include a local
or configured remote host label; opaque IDs in bindings/ownership carry the host.
The user can ask about remote projects by name. Dispatch still requires a unique
exact task title; duplicate names across hosts are rejected rather than guessed.
Host/path configuration and arbitrary SSH commands are not chat commands.
