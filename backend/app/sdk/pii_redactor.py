"""
Lightweight PII redaction using regex patterns.
Redacts: emails, phone numbers, SSNs, credit cards, API keys, IP addresses.
"""
import re
from typing import Optional

# Ordered from most-specific to least-specific to avoid partial matches
PII_PATTERNS = [
    # Credit card numbers (Visa, MC, Amex, Discover)
    (re.compile(r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b"), "[CREDIT_CARD]"),
    # SSN
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    # API keys (common patterns: long alphanumeric with optional prefix)
    (re.compile(r"\b(?:sk|pk|api|key|token|secret)[-_]?[A-Za-z0-9_\-]{20,}\b", re.IGNORECASE), "[API_KEY]"),
    # Email addresses
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL]"),
    # Phone numbers (US-centric: +1, dashes, dots, spaces)
    (re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE]"),
    # IPv4 addresses
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP_ADDRESS]"),
]


def redact(text: Optional[str]) -> Optional[str]:
    """Apply all PII patterns to text and return redacted version."""
    if not text:
        return text
    for pattern, replacement in PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_preview(text: Optional[str], max_length: int = 200) -> Optional[str]:
    """Redact PII and truncate to max_length for preview storage."""
    if not text:
        return text
    redacted = redact(text)
    if len(redacted) > max_length:
        return redacted[:max_length] + "…"
    return redacted
