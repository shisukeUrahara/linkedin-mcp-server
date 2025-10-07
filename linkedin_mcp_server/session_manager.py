"""Session management utilities for multi-tenant LinkedIn MCP usage."""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from linkedin_scraper.exceptions import InvalidCredentialsError

from linkedin_mcp_server.exceptions import CredentialsNotFoundError


@dataclass
class SessionData:
    """Stored data for an authenticated LinkedIn session."""

    cookie: str


_session_lock = threading.Lock()
_sessions: Dict[str, SessionData] = {}


def _normalize_cookie_for_storage(cookie: str) -> Tuple[str, str]:
    """Normalize cookie input and return (stored_cookie, raw_cookie)."""

    normalized = cookie.strip()
    if not normalized:
        raise ValueError("Cookie cannot be empty")

    if normalized.startswith("li_at="):
        stored = normalized
        raw = normalized.split("li_at=", 1)[1]
    else:
        stored = f"li_at={normalized}"
        raw = normalized

    return stored, raw


def create_or_update_session(
    cookie: str,
    session_token: Optional[str] = None,
    validate_cookie: bool = False,
) -> Tuple[str, bool]:
    """Create a new session or update an existing session with a LinkedIn cookie."""

    stored_cookie, raw_cookie = _normalize_cookie_for_storage(cookie)

    validation_performed = False

    if validate_cookie:
        from linkedin_mcp_server.setup import test_cookie_validity

        if not test_cookie_validity(raw_cookie):
            raise InvalidCredentialsError(
                "Provided LinkedIn cookie is invalid or expired"
            )
        validation_performed = True

    token = session_token or secrets.token_urlsafe(16)

    from linkedin_mcp_server.drivers.chrome import close_driver

    with _session_lock:
        # Close any existing driver for this token before overwriting
        close_driver(token)
        _sessions[token] = SessionData(cookie=stored_cookie)

    return token, validation_performed


def create_session_from_credentials(
    email: str,
    password: str,
    session_token: Optional[str] = None,
) -> str:
    """Create or update a session by logging in with credentials to capture a cookie."""

    from linkedin_mcp_server.setup import capture_cookie_from_credentials

    raw_cookie = capture_cookie_from_credentials(email, password)
    token, _ = create_or_update_session(raw_cookie, session_token=session_token)
    return token


def get_session_cookie(session_token: str) -> str:
    """Retrieve the stored cookie for a session token."""

    with _session_lock:
        session = _sessions.get(session_token)
        if not session:
            raise CredentialsNotFoundError(
                f"No LinkedIn session found for token '{session_token}'"
            )
        return session.cookie


def close_session(session_token: str) -> bool:
    """Close and remove a specific session."""

    from linkedin_mcp_server.drivers.chrome import close_driver

    with _session_lock:
        removed = _sessions.pop(session_token, None)

    driver_closed = close_driver(session_token)
    return removed is not None or driver_closed


def close_all_sessions() -> int:
    """Close and remove all managed sessions."""

    from linkedin_mcp_server.drivers.chrome import close_all_drivers

    with _session_lock:
        count = len(_sessions)
        _sessions.clear()

    close_all_drivers()
    return count


def list_sessions() -> List[Dict[str, Any]]:
    """List known sessions and whether a driver is active for them."""

    from linkedin_mcp_server.drivers.chrome import get_active_driver

    with _session_lock:
        return [
            {
                "session_token": token,
                "has_driver": get_active_driver(token) is not None,
            }
            for token in _sessions.keys()
        ]
