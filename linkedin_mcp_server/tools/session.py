"""MCP tools for managing LinkedIn authentication sessions."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastmcp import FastMCP

from linkedin_mcp_server.error_handler import handle_tool_error
from linkedin_mcp_server.session_manager import (
    close_all_sessions,
    close_session,
    create_or_update_session,
    create_session_from_credentials,
    list_sessions,
)

logger = logging.getLogger(__name__)


def register_session_tools(mcp: FastMCP) -> None:
    """Register session management tools with the MCP server."""

    @mcp.tool()
    async def create_session_with_cookie(
        cookie: str,
        session_token: Optional[str] = None,
        validate_cookie: bool = False,
    ) -> Dict[str, Any]:
        """Register a LinkedIn session cookie and obtain a session token."""

        try:
            token, validated = create_or_update_session(
                cookie, session_token=session_token, validate_cookie=validate_cookie
            )
            logger.info("Session %s registered with cookie", token)
            return {
                "status": "success",
                "session_token": token,
                "validated": bool(validated),
            }
        except Exception as e:
            return handle_tool_error(e, "create_session_with_cookie")

    @mcp.tool()
    async def create_session_with_credentials(
        email: str,
        password: str,
        session_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Login with LinkedIn credentials and create a session token."""

        try:
            token = create_session_from_credentials(
                email, password, session_token=session_token
            )
            logger.info("Session %s created from credentials", token)
            return {
                "status": "success",
                "session_token": token,
            }
        except Exception as e:
            return handle_tool_error(e, "create_session_with_credentials")

    @mcp.tool()
    async def close_session(
        session_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Close a specific session or all sessions if no token is provided."""

        try:
            if session_token:
                closed = close_session(session_token)
                if closed:
                    return {
                        "status": "success",
                        "message": f"Closed session {session_token}",
                    }
                return {
                    "status": "not_found",
                    "message": f"No active session found for token {session_token}",
                }

            count = close_all_sessions()
            return {
                "status": "success",
                "message": f"Closed {count} managed session(s)",
            }
        except Exception as e:
            return handle_tool_error(e, "close_session")

    @mcp.tool()
    async def list_active_sessions() -> Dict[str, Any]:
        """List managed session tokens and driver status."""

        try:
            sessions = list_sessions()
            return {
                "status": "success",
                "sessions": sessions,
            }
        except Exception as e:
            return handle_tool_error(e, "list_active_sessions")
