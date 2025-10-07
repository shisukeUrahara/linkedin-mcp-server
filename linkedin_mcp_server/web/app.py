"""FastAPI application exposing session APIs and a lightweight chat UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from linkedin_mcp_server.session_manager import (
    close_all_sessions,
    close_session,
    create_or_update_session,
    create_session_from_credentials,
    list_sessions,
)
from linkedin_mcp_server.web.agent import agent

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="LinkedIn MCP Companion", version="1.0.0")


class CookieSessionRequest(BaseModel):
    cookie: str = Field(..., description="LinkedIn li_at cookie")
    session_token: Optional[str] = Field(
        default=None, description="Optional token to reuse"
    )
    validate_cookie: bool = Field(
        default=False, description="Set True to verify the cookie before storing"
    )


class CredentialSessionRequest(BaseModel):
    email: str
    password: str
    session_token: Optional[str] = Field(
        default=None, description="Optional token to reuse"
    )


class SessionResponse(BaseModel):
    status: str
    session_token: Optional[str] = None
    validated: Optional[bool] = None


class ChatRequest(BaseModel):
    session_token: str
    message: str


@app.get("/api/health")
def health() -> Dict[str, str]:
    """Simple health endpoint for uptime checks."""

    return {"status": "ok"}


@app.post("/api/sessions/cookie", response_model=SessionResponse)
def create_session_cookie(payload: CookieSessionRequest) -> SessionResponse:
    """Register a LinkedIn cookie and return a session token."""

    try:
        token, validated = create_or_update_session(
            payload.cookie,
            session_token=payload.session_token,
            validate_cookie=payload.validate_cookie,
        )
        return SessionResponse(status="success", session_token=token, validated=validated)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sessions/credentials", response_model=SessionResponse)
def create_session_credentials(payload: CredentialSessionRequest) -> SessionResponse:
    """Login with credentials and register a LinkedIn session."""

    try:
        token = create_session_from_credentials(
            payload.email, payload.password, session_token=payload.session_token
        )
        return SessionResponse(status="success", session_token=token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/sessions")
def list_active_sessions() -> Dict[str, Any]:
    """Return all known session tokens and driver status."""

    return {"sessions": list_sessions()}


@app.delete("/api/sessions/{session_token}")
def remove_session(session_token: str) -> Dict[str, Any]:
    """Remove a specific session token."""

    removed = close_session(session_token)
    if not removed:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success", "session_token": session_token}


@app.delete("/api/sessions")
def remove_all_sessions() -> Dict[str, Any]:
    """Remove every session token and close all browsers."""

    count = close_all_sessions()
    return {"status": "success", "closed": count}


@app.post("/api/chat")
async def chat(payload: ChatRequest) -> JSONResponse:
    """Handle chat requests by delegating to the simple LinkedIn agent."""

    if not payload.session_token:
        raise HTTPException(status_code=400, detail="session_token is required")

    response = await agent.handle_message(payload.session_token, payload.message)
    status_code = 200 if response.get("status") == "success" else 400
    return JSONResponse(content=response, status_code=status_code)


@app.get("/")
def index() -> FileResponse:
    """Serve the bundled single-page app."""

    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not built")
    return FileResponse(index_path)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str) -> FileResponse:
    """Fallback route so SPA deep links resolve correctly."""

    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return index()


def main() -> None:
    """Run the FastAPI app with uvicorn."""

    import uvicorn

    host = os.environ.get("LINKEDIN_MCP_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("LINKEDIN_MCP_WEB_PORT", "8100"))
    uvicorn.run("linkedin_mcp_server.web.app:app", host=host, port=port, reload=False)


__all__ = ["app", "main"]
