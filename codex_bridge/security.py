import re
from pathlib import Path, PureWindowsPath, PurePosixPath


def lexical_inside(candidate, root, windows=False):
    """Platform-independent lexical check, before native symlink resolution."""
    cls = PureWindowsPath if windows else PurePosixPath
    child, parent = cls(candidate), cls(root)
    if not child.is_absolute() or not parent.is_absolute() or '..' in child.parts:
        return False
    return child == parent or parent in child.parents


def allowed_path(value, roots):
    if not isinstance(value, str) or not value or '\x00' in value:
        return None
    p = Path(value)
    if not p.is_absolute() or '..' in p.parts:
        return None
    try:
        real = p.resolve(strict=True)
        if not real.is_dir():
            return None
        for root in roots:
            canonical = root.resolve(strict=True)
            if real == canonical or canonical in real.parents:
                return real
    except (OSError, ValueError, RuntimeError):
        pass
    return None


def safe_text(text, limit=3000, secrets=()):
    text = str(text)
    for secret in sorted((x for x in secrets if x), key=len, reverse=True):
        text = text.replace(secret, '[redacted]')
    text = re.sub(r'https?://[^\s<>]+', '[link omitted]', text)
    text = re.sub(r'(?i)(?:[a-z]:[\\/]|\\\\)[^\s<>"\r\n]+', '[path]', text)
    text = re.sub(r'(?<![\w:])/(?:[^\s/<>]+/)+[^\s<>]*', '[path]', text)
    text = re.sub(r'(?<![\w:])/(?:home|Users|tmp|var|etc|opt|usr|root|mnt|Volumes|private)(?=\s|$)', '[path]', text)
    text = re.sub(r'(?i)(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}', '[redacted]', text)
    text = re.sub(r'(?im)^.*(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=].*$', '[sensitive line omitted]', text)
    text = ''.join(c for c in text if c in '\n\t' or ord(c) >= 32)
    suffix = '\n… [已截断，请在本机查看完整结果]'
    return text if len(text) <= limit else text[:max(0, limit-len(suffix))] + suffix
