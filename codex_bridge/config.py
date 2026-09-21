import json
import os
import shutil
import re
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath


class ConfigError(ValueError):
    pass


@dataclass(frozen=True, repr=False)
class RemoteConfig:
    alias: str
    host: str
    command: str
    home: str
    roots: tuple


def remote_configs(raw):
    try:
        values = json.loads(raw)
        if not isinstance(values, list) or len(values) > 4:
            raise ValueError()
        result, aliases = [], set()
        for entry in values:
            if not isinstance(entry, dict) or set(entry) != {'alias','host','command','home','roots'}:
                raise ValueError()
            alias, host = entry['alias'], entry['host']
            if not isinstance(alias,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,24}',alias) or alias == 'local' or alias in aliases:
                raise ValueError()
            if not isinstance(host,str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}',host):
                raise ValueError()
            roots = entry['roots']
            if not isinstance(roots,list) or not 1 <= len(roots) <= 32:
                raise ValueError()
            for value in [entry['command'],entry['home'],*roots]:
                if not isinstance(value,str) or not value or len(value)>4096 or any(ord(c)<32 for c in value):
                    raise ValueError()
                p=PurePosixPath(value)
                if not p.is_absolute() or '..' in p.parts or str(p)=='/' or value.startswith('//'):
                    raise ValueError()
            aliases.add(alias)
            result.append(RemoteConfig(alias,host,entry['command'],entry['home'],tuple(roots)))
        return tuple(result)
    except (ValueError,KeyError,TypeError):
        raise ConfigError('Invalid fixed SSH remote configuration') from None


def load_env(path):
    values = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, sep, value = line.partition('=')
            if not sep:
                raise ConfigError('Invalid local configuration line')
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key.strip()] = value
    values.update(os.environ)
    return values


@dataclass(repr=False)
class Config:
    client_id: str
    client_secret: str
    users: frozenset
    conversations: frozenset
    roots: tuple
    command: str
    state_path: Path
    codex_home: str = ''
    max_input: int = 4000
    max_output: int = 3000
    remotes: tuple = ()

    @classmethod
    def load(cls, directory, env=None):
        e = load_env(directory / '.env') if env is None else env
        required = ('DINGTALK_CLIENT_ID', 'DINGTALK_CLIENT_SECRET', 'DINGTALK_ALLOWED_USER_IDS', 'CODEX_ALLOWED_ROOTS')
        if any(not e.get(k, '').strip() for k in required):
            raise ConfigError('Missing credentials, allowed users or allowed roots; see .env.example')
        if e.get('CODEX_REMOTE_APPROVAL_POLICY', 'never') != 'never' or e.get('CODEX_REMOTE_SANDBOX', 'workspaceWrite') != 'workspaceWrite':
            raise ConfigError('Only workspaceWrite and never are supported')
        if e.get('BRIDGE_CHANNEL', 'dingtalk') != 'dingtalk':
            raise ConfigError('Only DingTalk is supported')
        try:
            raw = json.loads(e['CODEX_ALLOWED_ROOTS'])
            if not isinstance(raw, list) or not raw:
                raise ValueError()
            roots = []
            for p in raw:
                if not isinstance(p, str) or not Path(p).is_absolute():
                    raise ValueError()
                resolved = Path(p).resolve(strict=True)
                if not resolved.is_dir():
                    raise ValueError()
                roots.append(resolved)
            max_input = int(e.get('BRIDGE_MAX_INPUT_CHARS', 4000))
            max_output = int(e.get('BRIDGE_MAX_OUTPUT_CHARS', 3000))
            if not 1 <= max_input <= 16000 or not 300 <= max_output <= 10000:
                raise ValueError()
        except (ValueError, TypeError, OSError, RuntimeError):
            raise ConfigError('Invalid roots JSON, unavailable directory or message limits') from None
        command = shutil.which(e.get('CODEX_COMMAND', 'codex'))
        if not command or Path(command).suffix.lower() in ('.cmd', '.bat', '.ps1'):
            raise ConfigError('Set CODEX_COMMAND to the native Codex executable, not a shell shim')
        users = frozenset(x.strip() for x in e['DINGTALK_ALLOWED_USER_IDS'].split(',') if x.strip())
        if not users:
            raise ConfigError('Allowed users must not be empty')
        state = Path(e.get('BRIDGE_STATE_PATH', '.data/bridge.db'))
        if not state.is_absolute():
            state = directory / state
        remotes = remote_configs(e.get('CODEX_SSH_REMOTES','[]'))
        if remotes and not shutil.which('ssh'):
            raise ConfigError('OpenSSH is required for configured remotes')
        return cls(e['DINGTALK_CLIENT_ID'], e['DINGTALK_CLIENT_SECRET'], users,
                   frozenset(x.strip() for x in e.get('DINGTALK_ALLOWED_CONVERSATION_IDS', '').split(',') if x.strip()),
                   tuple(roots), command, state, e.get('CODEX_HOME', ''), max_input, max_output, remotes)
