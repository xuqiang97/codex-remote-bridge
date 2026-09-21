"""Run with Python 3.10+ from this repository's virtual environment."""
import argparse
import asyncio
import logging
from pathlib import Path

from codex_bridge.backends import Backends
from codex_bridge.config import Config, ConfigError
from codex_bridge.coordinator import Coordinator
from codex_bridge.state import State


async def run(config):
    from channels.dingtalk import DingTalk
    state = State(config.state_path)
    app = Backends(config)
    router = Coordinator(config, state, app)
    channel = DingTalk(config, router)
    try:
        await app.start()
        print('Bridge ready. Private allowlisted conversations only.', flush=True)
        await channel.run()
    finally:
        router.closing = True
        await channel.close()
        await router.close()
        state.close()


def main():
    parser = argparse.ArgumentParser(description='Local DingTalk to existing Codex thread bridge')
    parser.add_argument('--check', action='store_true', help='Validate local configuration without network or Codex')
    args = parser.parse_args()
    # Third-party logs can contain callback URLs, tickets, paths or payloads.
    logging.disable(logging.CRITICAL)
    try:
        config = Config.load(Path(__file__).resolve().parent)
        if args.check:
            print('Configuration valid; secrets omitted.'); return
        asyncio.run(run(config))
    except KeyboardInterrupt:
        print('Bridge stopped.')
    except ConfigError as exc:
        print(str(exc)); raise SystemExit(2)
    except Exception:
        print('Bridge stopped safely. Check local Codex login, executable and configuration. Details suppressed to protect secrets.')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
