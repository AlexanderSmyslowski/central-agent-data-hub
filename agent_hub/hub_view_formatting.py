"""Shared display formatting for Hub View models."""

from __future__ import annotations

from datetime import datetime, timezone


def format_timestamp(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    text = str(value)
    return text.replace("T", " ").replace("+00:00", " UTC")
