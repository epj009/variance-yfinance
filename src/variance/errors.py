"""
Error helpers for user-facing diagnostics.
"""

from collections.abc import Mapping
from typing import Any, Optional


def build_error(
    error: str,
    *,
    details: Optional[str] = None,
    hint: Optional[str] = None,
    warning_detail: Optional[Mapping[str, Any]] = None,
    warning_message: Optional[str] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": error}
    if details:
        payload["details"] = details
    if hint:
        payload["hint"] = hint
    if warning_detail:
        payload["warning_detail"] = dict(warning_detail)
    if warning_message:
        payload["warning_message"] = warning_message
    return payload


def warning_detail_message(data: Mapping[str, Any]) -> Optional[str]:
    warning_detail = data.get("warning_detail") or {}
    if isinstance(warning_detail, Mapping):
        message = warning_detail.get("message")
        if message:
            return str(message)
    warning_message = data.get("warning_message")
    return str(warning_message) if warning_message else None


def error_lines(payload: Mapping[str, Any]) -> list[str]:
    lines = []
    error = payload.get("error") or "Unknown error."
    lines.append(f"Error: {error}")
    details = payload.get("details")
    if details:
        lines.append(f"Details: {details}")
    hint = payload.get("hint")
    if hint:
        lines.append(f"Hint: {hint}")
    warning_message = warning_detail_message(payload)
    if warning_message:
        lines.append(f"Warning: {warning_message}")
    return lines
