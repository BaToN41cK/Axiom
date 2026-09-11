"""Utility functions."""

import re
from datetime import datetime


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.0f}s"


def format_number(num: int | float) -> str:
    """Format number with K/M suffix."""
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K"
    return str(num)


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def clean_whitespace(text: str) -> str:
    """Clean excessive whitespace from text."""
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            cleaned_lines.append(stripped)
    return "\n".join(cleaned_lines)


def extract_urls(text: str) -> list[str]:
    """Extract URLs from text."""
    url_pattern = r"https?://[^\s<>\"]+|www\.[^\s<>\"]+"
    return re.findall(url_pattern, text)


def timestamp() -> str:
    """Get current timestamp string."""
    return datetime.now().strftime("%H:%M:%S")
