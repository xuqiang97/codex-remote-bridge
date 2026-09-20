# Security Model

`codex-remote-bridge` is remote-control software for a local coding agent.

A chat message can cause Codex to read and modify files inside a workspace. Treat every design decision accordingly.

## 1. Security objective

V1 should let one explicitly trusted human continue an existing Codex thread remotely while preventing:

- unauthorized users from controlling Codex;
- remote privilege escalation;
- arbitrary shell access;
- access to unapproved projects;
- duplicate/replayed messages from creating duplicate work;
- accidental exposure of local paths, prompts, source code, or credentials;
- accidental public exposure of the Codex app-server.

Availability is secondary to safety. When uncertain, fail closed.

## 2. Trust boundaries

```text
[DingTalk user]
      |
      | untrusted network/platform transport
      v
[DingTalk Stream SDK]
      |
      | normalized inbound message
      v
[Authorization + router]  <---- local config/secrets
      |
      | trusted command after checks
      v
[Codex bridge]
      |
      | local stdio only
      v
[codex app-server]
      |
      | sandboxed Codex work
      v
[allowed local workspace]
```

The bridge must not assume that a message is safe merely because DingTalk delivered it.

## 3. Identity and authorization

Use stable DingTalk IDs, not names.

Required:

- explicit allowed user IDs;
- default deny;
- optional allowed conversation IDs;
- 1:1/private conversation as the recommended V1 mode.

If group messages are ever enabled:

- group/conversation ID must be allowlisted;
- sender ID must also be allowlisted;
- mention/display name is not authorization.

Do not reveal thread/project information to unauthorized senders.

## 4. Secrets

Sensitive local values include:

- DingTalk client ID if organizational policy treats it as sensitive;
- DingTalk client secret;
- future channel tokens;
- local environment overrides.

Rules:

- never commit them;
- do not store them in SQLite;
- do not print them in logs/exceptions;
- prefer environment variables or a local ignored `.env`;
- redact configuration representations.

Public `.env.example` values must be unusable placeholders.

## 5. No public Codex listener

V1 starts:

```text
codex app-server
```

as a child process and communicates over stdio.

Do not bind app-server to:

- `0.0.0.0`;
- LAN IPs;
- public IPs;
- tunnels;
- public WebSocket endpoints.

Even a localhost WebSocket listener is unnecessary for V1 unless the owner explicitly changes the design.

## 6. Stable API only

Do not set:

```json
"experimentalApi": true
```

V1 should use stable documented app-server behavior only.

This limits surprise surface and avoids depending on unstable permission/tool methods.

## 7. Remote sandbox posture

Remote turns should be more restrictive than local interactive turns.

Default target:

```text
approvalPolicy=never
sandbox=workspaceWrite
```

Do not provide a configuration option for `dangerFullAccess` in V1.

If platform/Codex semantics change, preserve the intent:

> remote chat may work inside explicitly allowed workspaces but must never gain elevated access through a chat approval.

## 8. Approval requests

The app-server can issue server-initiated requests for command execution, file changes, permissions, user input, MCP elicitation, and other actions.

V1 MUST NOT turn DingTalk into an approval console.

For any approval-style server request:

- never send `accept`;
- never send `acceptForSession`;
- never grant additional filesystem/network permissions;
- choose the safest documented decline/cancel response;
- tell the trusted user that local attention is required;
- avoid including raw command/path details in the chat reply.

Remote approval is a separate future security project.

## 9. Prohibited app-server methods

The bridge must not expose generic RPC passthrough.

Explicitly prohibit remote access to:

- `thread/shellCommand`;
- `command/exec`;
- `command/exec/write`;
- `command/exec/resize`;
- config write methods;
- thread deletion;
- arbitrary MCP calls;
- dynamic tools;
- experimental methods.

Important: official Codex documentation states `thread/shellCommand` runs outside the thread sandbox with full access. It must never be mapped to chat commands.

## 10. Project-root allowlist

`CODEX_ALLOWED_ROOTS` is mandatory for V1.

The bridge must not list every stored thread.

Rules:

- canonicalize each configured root;
- canonicalize each candidate thread cwd;
- require candidate cwd to be the root itself or a descendant;
- handle Windows drive/UNC semantics correctly;
- handle POSIX paths correctly;
- resolve symlinks where practical before authorization;
- reject missing/relative/ambiguous cwd values;
- never accept a cwd/path supplied by DingTalk.

Chat output should show only a project basename/alias, never the full path.

## 11. Existing-thread handoff safety

The target use case is a thread whose previous Desktop turn has completed.

Do not attempt to take over a thread while another client is actively executing a turn.

The bridge should:

- inspect available thread status before starting;
- refuse if status indicates active work not owned by this bridge;
- maintain local ownership metadata for turns it starts.

If cross-client activity cannot be determined reliably, prefer refusal over concurrent mutation.

## 12. Turn ownership

`/stop` is dangerous if it can cancel another client's work.

V1 rule:

- the bridge may interrupt only a turn it started and is currently tracking;
- do not send `turn/interrupt` merely because a thread is active;
- clear ownership on completion/interruption/process restart.

A process restart loses in-memory ownership. After restart, do not assume an active turn belongs to the bridge.

## 13. Message replay and deduplication

Stream/event delivery may retry.

Before invoking Codex:

1. authenticate sender;
2. check message ID in durable dedupe store;
3. atomically mark/reserve the message;
4. only then perform side effects.

A repeated message must not create a second Codex turn.

Keep dedupe retention bounded.

## 14. Input constraints

V1 accepts text only.

Apply:

- maximum input length;
- trim empty messages;
- strict command parsing;
- no implicit shell syntax;
- no file uploads;
- no URLs that trigger special execution behavior;
- no arbitrary serialized JSON-RPC from the user.

Ordinary text is passed only as a Codex user text input after authorization/binding checks.

## 15. Output constraints

Codex output may contain secrets or sensitive local information.

V1 should return the final assistant-facing message, but:

- cap length;
- avoid raw command output;
- avoid raw tool payloads;
- strip/replace full absolute paths where practical;
- never include environment variables;
- never include app-server protocol messages;
- do not send complete thread history.

For highly sensitive repositories, remote bridge should simply be disabled.

## 16. Logging

Production/default logs should contain only operational metadata.

Good:

```text
message accepted channel=dingtalk sender=<hash>
turn started thread=thr_... project=codex-notify
turn completed status=completed
```

Avoid:

```text
user said: <full prompt>
running command: <full command>
cwd=C:\Users\...
assistant: <full response>
client_secret=...
```

If debug logging is added, it must be opt-in and loudly documented.

## 17. Local state security

Preferred V1 state is SQLite.

State file contains bindings/dedupe only.

It should not contain:

- channel secrets;
- prompts;
- assistant responses;
- source code;
- commands;
- absolute paths when avoidable.

Document recommended local file permissions.

## 18. Dependency security

Direct dependency surface should remain small.

For DingTalk, the official Stream SDK is justified.

Pin a tested compatible version/range deliberately. Do not add general-purpose web frameworks or remote-control packages without need.

Public CI must not require secrets.

## 19. Multi-device warning

Running the same bot credential simultaneously on multiple computers is not a supported V1 routing design.

Do not assume Stream delivery will fan out deterministically to all machines.

V1 should use:

- one designated bridge host per bot/app identity; or
- separate bot/app credentials per independent host.

A real multi-device router/relay is V2 work.

## 20. Incident-safe defaults

On:

- malformed DingTalk event;
- unknown sender;
- stale binding;
- disallowed cwd;
- app-server error;
- approval request;
- unknown RPC request;
- duplicate message;
- bridge restart ambiguity;

the safe behavior is to perform no local side effect.

## 21. Security review checklist before V1 release

Confirm all are true:

- [ ] secrets absent from Git history;
- [ ] sender allowlist mandatory;
- [ ] group chat disabled or explicitly restricted;
- [ ] project allowlist mandatory;
- [ ] no public app-server listener;
- [ ] experimental API disabled;
- [ ] no shell-command endpoint;
- [ ] no remote approvals;
- [ ] dedupe durable;
- [ ] per-thread concurrency controlled;
- [ ] `/stop` ownership enforced;
- [ ] tests prove unauthorized messages cannot call Codex;
- [ ] tests prove approval requests cannot be accepted;
- [ ] logs do not contain prompts/secrets/full paths;
- [ ] real end-to-end validation uses a disposable/safe test repository first.
