# codex-remote-bridge

Continue a local Codex conversation from a trusted chat channel when you are away from the computer.

> **Status:** architecture/specification stage. V1 is intentionally not implemented yet. The next coding agent should follow `AGENTS.md` and the documents under `docs/`.

## Why this project exists

`codex-notify` answers:

> “My local Codex task finished. Tell my phone.”

`codex-remote-bridge` answers the next question:

> “I saw the notification. Can I send a follow-up from DingTalk and continue the same local Codex thread without opening remote desktop?”

The intended V1 flow is:

```text
DingTalk mobile / desktop
        |
        | DingTalk Stream Mode (outbound long connection from the computer)
        v
codex-remote-bridge
        |
        | local stdio JSON-RPC
        v
codex app-server
        |
        | thread/resume + turn/start
        v
existing local Codex thread
        |
        | final result
        v
DingTalk reply
```

No public HTTP server is required for V1.

## V1 decisions

- **Language:** Python 3.10+.
- **First chat channel:** DingTalk.
- **DingTalk transport:** official Stream Mode Python SDK.
- **Codex integration:** official `codex app-server`.
- **App-server transport:** child process over **stdio**.
- **No public app-server WebSocket/TCP listener.**
- **Stable APIs only:** do not enable `experimentalApi` in V1.
- **Primary use case:** resume an already completed local Codex thread and start a new turn.
- **Remote approval:** not supported in V1.
- **Remote execution posture:** conservative sandbox, no elevation, no arbitrary shell endpoint.
- **State:** local-only, minimal durable mapping/deduplication.
- **Future channels:** Feishu and others should fit behind a small channel adapter boundary.

Official Codex app-server documentation:
- https://developers.openai.com/docs/app-server

Official DingTalk Stream Python SDK:
- https://github.com/open-dingtalk/dingtalk-stream-sdk-python

## Critical V1 go/no-go spike

The most important assumption must be validated before building the full bridge:

> A thread created/used by Codex Desktop on the same machine can be resumed by a separately started `codex app-server` process running under the same user/Codex home after the Desktop turn has completed.

The implementation agent must test this first.

If that handoff does **not** work reliably, do not fake it. Record the result and fall back to supporting only threads created/managed by the bridge until a supported handoff is available.

## V1 user interaction

The bot should use a small command surface.

```text
/threads
/current
/use <index>
/unbind
/stop
/help
```

After a thread is bound to the current trusted conversation, ordinary text starts a new Codex turn in that thread.

Example:

```text
User: /threads
Bot:
1. codex-notify — “Review ntfy provider”
2. amazon-asin-image-hub — “Update A+ aggregation”

User: /use 1
Bot: Bound to codex-notify.

User: Continue. Tighten the README and rerun the tests.
Bot: Started on codex-notify.
...
Bot: Completed.
     <concise final Codex response>
```

V1 should **not** silently steer a currently running turn. If the selected thread is active, reject the new instruction and tell the user to wait or use `/stop`.

## Security posture

This project controls a local coding agent. Treat it as remote administration software even though the UX is a chat bot.

V1 requirements:

- use a strict sender allowlist;
- prefer 1:1/private bot conversations;
- optionally allowlist conversation IDs;
- filter visible threads to configured allowed project roots;
- never expose arbitrary `cwd` selection through chat;
- never expose `thread/shellCommand`;
- never expose `command/exec`;
- never start app-server on a public interface;
- never auto-accept command/file/network permission requests;
- remote turns should use a conservative approval/sandbox policy;
- deduplicate inbound message IDs;
- serialize work per Codex thread;
- avoid logging full prompts, code, credentials, or Codex outputs by default;
- keep DingTalk secrets and local state out of Git.

Read [docs/SECURITY.md](docs/SECURITY.md) before implementation.

## Relationship to codex-notify

This repository is a sibling project, not a replacement:

- `codex-notify`: one-way “Codex completed” mobile push.
- `codex-remote-bridge`: authenticated chat input back into local Codex.

V1 does not import or modify `codex-notify`.

A later integration may use the completion hook's `thread-id` to make binding the just-finished thread easier, but that is explicitly outside the first implementation.

## Planned repository shape

```text
codex-remote-bridge/
├── AGENTS.md
├── README.md
├── LICENSE
├── .env.example
├── .gitignore
├── bridge.py
├── codex_bridge/
│   ├── __init__.py
│   ├── app_server.py
│   ├── config.py
│   ├── router.py
│   └── state.py
├── channels/
│   ├── __init__.py
│   ├── base.py
│   └── dingtalk.py
├── tests/
└── docs/
    ├── DECISIONS.md
    ├── IMPLEMENTATION.md
    ├── PROTOCOL.md
    └── SECURITY.md
```

The implementation agent may simplify the exact package layout if responsibilities remain separated and the security/acceptance requirements are preserved.

## Suggested configuration

Real values belong only in local configuration.

```env
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

See `.env.example` for comments and safe placeholders.

## Implementation order

Do not start by building the DingTalk UI.

The required sequence is:

1. Validate same-machine Desktop-thread -> app-server `thread/resume` handoff.
2. Build and test a local app-server client over stdio.
3. Implement conservative thread listing/filtering/binding.
4. Add DingTalk Stream inbound/outbound adapter.
5. Add authentication/allowlist/deduplication.
6. Run offline tests.
7. Run real DingTalk -> local Codex -> DingTalk end-to-end validation.

See [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md).

## Non-goals for V1

- Feishu implementation.
- Multiple computers behind one shared bot identity.
- Central cloud relay.
- Remote command/file approval.
- Remote permission elevation.
- Arbitrary shell execution.
- Arbitrary project/cwd selection.
- Streaming every token to DingTalk.
- Rich AI cards.
- Voice/image/file input.
- Starting a new Codex thread remotely.
- Remote control of a turn that is concurrently active in Codex Desktop.
- Public web dashboard.
- SaaS hosting.

## License

MIT.
