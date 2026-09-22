"""FastAPI service entrypoint for Trackmania Tracker."""

import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from authentication import (
    PasswordConfigurationError,
    UbisoftAuthenticationError,
    ensure_nadeo_service_token,
    get_nadeo_service_token,
    verify_app_password,
)
import live_services
from logger import get_logger

logger = get_logger("api")


def _application_version() -> str:
    try:
        return version("tm-tracker")
    except PackageNotFoundError:
        return "0.1.0"


APPLICATION_VERSION = _application_version()

app = FastAPI(
    title="Trackmania Bingo API",
    version=APPLICATION_VERSION,
    description="Decoupled backend API for Trackmania Bingo",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_token_lock = Lock()
_service_token: dict[str, Any] | None = None


def get_current_service_token() -> str:
    """Thread-safe acquisition and refresh of the shared Nadeo service token."""

    global _service_token  # pylint: disable=global-statement
    with _token_lock:
        if _service_token is None:
            _service_token = get_nadeo_service_token()
        else:
            _service_token = ensure_nadeo_service_token(_service_token)
        return str(_service_token["accessToken"])


def set_cached_service_token(token: dict[str, Any] | None) -> None:
    """Seam for testing service token behavior without network calls."""

    global _service_token  # pylint: disable=global-statement
    with _token_lock:
        _service_token = token


@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Log structured HTTP request metadata with duration in milliseconds."""

    start_time = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start_time) * 1000, 2)
    logger.info(
        f"{request.method} {request.url.path} {response.status_code} ({duration_ms}ms)",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": request.client.host if request.client else None,
        },
    )
    return response


class VerifyPasswordRequest(BaseModel):
    password: str


class VerifyPasswordResponse(BaseModel):
    authenticated: bool


class CampaignResponse(BaseModel):
    campaign_id: str
    name: str


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Return health status of the API service."""

    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "version": APPLICATION_VERSION,
    }


@app.get("/api/version", tags=["system"])
def api_version() -> dict[str, str]:
    """Return application version information."""

    return {"version": APPLICATION_VERSION}


@app.post("/api/auth/verify", response_model=VerifyPasswordResponse, tags=["auth"])
def verify_password(payload: VerifyPasswordRequest) -> VerifyPasswordResponse:
    """Verify application password against PBKDF2 configuration."""

    try:
        is_valid = verify_app_password(payload.password)
    except PasswordConfigurationError as error:
        logger.error(
            "Password verification failed due to server configuration error",
            extra={"error": str(error)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        ) from error

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect application password.",
        )
    return VerifyPasswordResponse(authenticated=True)


@app.get("/api/campaigns", response_model=list[CampaignResponse], tags=["campaigns"])
def get_campaigns() -> list[CampaignResponse]:
    """Load official campaigns from Nadeo Live Services."""

    try:
        token = get_current_service_token()
        campaigns = live_services.get_official_campaigns(token)
    except UbisoftAuthenticationError as error:
        logger.error("Authentication failed during campaigns fetch", extra={"error": str(error)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to authenticate with Nadeo Live Services.",
        ) from error
    except live_services.LiveServiceError as error:
        logger.error(
            "Live services error during campaigns fetch",
            extra={"category": error.category, "status_code": error.status_code},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error

    return [
        CampaignResponse(campaign_id=c.campaign_id, name=c.name)
        for c in campaigns
    ]
