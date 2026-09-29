"""
Redaction module — strips secrets, credentials, and HTML/script injection from
any text retrieved from AWS resources before it is shown to the user or fed
back into the LLM context.

Design goals:
  - Redact conservatively: better to over-redact than leak a real secret.
  - Never block the pipeline on a redaction error — fall back to a safe string.
  - Treat AWS resource text as untrusted (prompt-injection guard).
"""

import html
import re
from typing import Final

# ── Regex patterns ────────────────────────────────────────────────────────────

# AWS access key IDs  (AKIA…, ASIA…, AROA…, AIDA…, AGPA…, ANPA…, ANVA…, APKA…)
_AWS_KEY_ID: Final = re.compile(
    r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}",
    re.ASCII,
)

# AWS secret access keys — 40-char base64-ish strings that follow "secret" keywords
_AWS_SECRET_KEY: Final = re.compile(
    r"""(?i)(?:secret[_\-\s]?(?:access[_\-\s]?)?key|aws[_\-\s]?secret)\s*[=:]\s*["']?([A-Za-z0-9+/]{40})["']?""",
    re.MULTILINE,
)

# STS session tokens — long base64 strings (300–1000 chars)
_SESSION_TOKEN: Final = re.compile(
    r"""(?i)(?:session[_\-\s]?token|aws[_\-\s]?session[_\-\s]?token)\s*[=:]\s*["']?([A-Za-z0-9+/=]{100,1000})["']?""",
    re.MULTILINE,
)

# Generic key=value / key: value patterns for common secret field names
# Also catches HTTP Authorization header style: "bearer <token>"
_GENERIC_SECRET: Final = re.compile(
    r"""(?i)(?:password|passwd|secret|token|api[_\-]?key|private[_\-]?key|auth[_\-]?token)\s*[=:]\s*["']?(\S{8,})["']?""",
    re.MULTILINE,
)
# Separate pattern for bearer tokens (space-separated, no = or :)
_BEARER_TOKEN: Final = re.compile(
    r"""(?i)\bbearer\s+([A-Za-z0-9\-_+/=.]{8,})""",
    re.MULTILINE,
)

# Long base64-looking standalone blobs (e.g. encoded certs, embedded JWT payloads)
_LONG_BASE64: Final = re.compile(r"[A-Za-z0-9+/]{120,}={0,2}")

# HTML / script tags — prompt-injection guard
_HTML_TAGS: Final = re.compile(r"<[^>]{1,200}>", re.DOTALL)

# Markdown-style links that could embed javascript: URIs
_DANGEROUS_LINKS: Final = re.compile(
    r"\[([^\]]{0,200})\]\((?:javascript:|data:)[^)]{0,500}\)",
    re.IGNORECASE,
)

_REDACTED: Final = "[REDACTED]"


# ── Public API ────────────────────────────────────────────────────────────────


def redact(text: str) -> str:
    """
    Apply all redaction rules to *text* and return the sanitised string.

    Always returns a string — never raises.
    """
    try:
        return _apply_all(text)
    except Exception:  # noqa: BLE001  # pragma: no cover
        return "[Content redacted due to processing error]"


def redact_dict(obj: object) -> object:
    """
    Recursively redact all string values inside a dict/list/str structure.
    Non-string leaf values are returned unchanged.
    """
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: redact_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_dict(item) for item in obj]
    return obj


# ── Internal ──────────────────────────────────────────────────────────────────


def _apply_all(text: str) -> str:
    # 1. HTML-encode any embedded tags to neutralise script injection
    text = _HTML_TAGS.sub(lambda m: html.escape(m.group(0)), text)

    # 2. Strip dangerous markdown links
    text = _DANGEROUS_LINKS.sub(r"[\1]([link removed])", text)

    # 3. Redact AWS key IDs (standalone)
    text = _AWS_KEY_ID.sub(_REDACTED, text)

    # 4. Redact AWS secret keys (key=value form — group 1 is the secret value)
    text = _AWS_SECRET_KEY.sub(lambda m: m.group(0).replace(m.group(1), _REDACTED), text)

    # 5. Redact STS session tokens
    text = _SESSION_TOKEN.sub(lambda m: m.group(0).replace(m.group(1), _REDACTED), text)

    # 6. Redact generic secret fields
    text = _GENERIC_SECRET.sub(lambda m: m.group(0).replace(m.group(1), _REDACTED), text)

    # 7. Redact bearer tokens (Authorization header style)
    text = _BEARER_TOKEN.sub(lambda m: m.group(0).replace(m.group(1), _REDACTED), text)

    # 8. Redact long base64 blobs (likely embedded tokens or certs)
    text = _LONG_BASE64.sub(_REDACTED, text)

    return text
