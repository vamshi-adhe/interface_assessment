import os
import re
from urllib.parse import urlparse

ALLOWED_ACTIONS = {"navigate", "click", "type", "read", "assert", "wait"}
IRREVERSIBLE_KEYWORDS = {"delete", "transfer", "confirm", "withdraw"}

def _allowed_domains():
    return [d.strip() for d in os.getenv("ALLOWED_DOMAINS", "localhost,127.0.0.1").split(",")]

def assert_safe(action: str, url: str, value: str = "") -> None:
    """Raise PermissionError if the action violates policy."""
    if action not in ALLOWED_ACTIONS:
        raise PermissionError(f"Action '{action}' is not in the allowed list.")
    hostname = urlparse(url).hostname or ""
    if not any(hostname == d or hostname.endswith(f".{d}") for d in _allowed_domains()):
        raise PermissionError(f"Domain '{hostname}' is not in the allowed domain list.")

def classify_risk(action: str, value: str = "") -> str:
    val = (value or "").lower()
    if any(kw in val for kw in IRREVERSIBLE_KEYWORDS):
        return "irreversible"
    if action == "navigate" and "transfer" in val:
        return "risky"
    return "safe"

_PII_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED-SSN]"),
    (re.compile(r"\b\d{13,19}\b"),           "[REDACTED-CARD]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED-EMAIL]"),
]

def redact(text: str) -> str:
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text