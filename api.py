"""FastAPI service entrypoint for Trackmania Tracker."""

import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from threading import Lock
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import live_services
from authentication import (
    PasswordConfigurationError,
    UbisoftAuthenticationError,
    ensure_nadeo_service_token,
    get_nadeo_service_token,
    verify_app_password,
)
from bingo import (
    BingoSettings,
    ManualTimerState,
    TrackRanking,
    build_bingo_grid,
    grace_period_active,
    manual_timer_remaining,
)
from bingo_service import (
    SHARED_CANONICAL_GAME,
    SHARED_MANUAL_TIMER,
    CanonicalGameAlreadyStartedError,
    CanonicalGameNotStartedError,
    CanonicalGameState,
    PendingGame,
    RecordEntry,
    poll_canonical_game,
    reset_canonical_game,
    start_canonical_game,
    stop_canonical_game,
)
from logger import get_logger
from player import PLAYERS, Player
from storage import create_game_state_store
from track import Track

logger = get_logger("api")


def _application_version() -> str:
    try:
        return version("tm-tracker")
    except PackageNotFoundError:
        return "0.1.0"


APPLICATION_VERSION = _application_version()


def init_storage(persistence: Any = None) -> None:
    """Wire persistence and rehydrate in-flight session and player timers."""

    store = persistence if persistence is not None else create_game_state_store()
    SHARED_CANONICAL_GAME.set_persistence(store, SHARED_MANUAL_TIMER)
    if SHARED_CANONICAL_GAME.rehydrate():
        logger.info("Storage initialized: rehydrated active session from persistence")
    else:
        logger.info("Storage initialized: clean pending state")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Lifespan context manager ensuring storage is initialized and rehydrated."""

    if not SHARED_CANONICAL_GAME.has_persistence:
        init_storage()
    else:
        SHARED_CANONICAL_GAME.rehydrate()
    yield


app = FastAPI(
    title="Trackmania Bingo API",
    version=APPLICATION_VERSION,
    description="Decoupled backend API for Trackmania Bingo",
    lifespan=lifespan,
)

init_storage()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_token_lock = Lock()
_service_token: dict[str, Any] | None = None  # pylint: disable=invalid-name


def get_current_service_token() -> str:
    """Thread-safe acquisition and refresh of the shared Nadeo service token."""

    global _service_token  # pylint: disable=global-statement
    with _token_lock:
        if _service_token is None:
            _service_token = get_nadeo_service_token()
        else:
            _service_token = cast(
                dict[str, Any], ensure_nadeo_service_token(_service_token)
            )
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
        "%s %s %s (%sms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
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
        logger.error(
            "Authentication failed during campaigns fetch", extra={"error": str(error)}
        )
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

    return [CampaignResponse(campaign_id=c.campaign_id, name=c.name) for c in campaigns]


# Game & Timer Serializers


def _serialize_player(player: Player | None) -> dict[str, Any] | None:
    if player is None:
        return None
    return {"account_id": player.account_id, "name": player.name}


def _serialize_track(track: Track) -> dict[str, Any]:
    return {
        "uid": track.uid,
        "name": track.name,
        "number": track.number,
    }


def _serialize_cell(cell: Any) -> dict[str, Any]:
    return {
        "track": _serialize_track(cell.track),
        "rankings": [
            {"player": _serialize_player(r.player), "time": r.time}
            for r in cell.rankings
        ],
        "owner": _serialize_player(cell.owner),
        "margin": cell.margin,
    }


def _serialize_record(entry: RecordEntry) -> dict[str, Any]:
    return {
        "observed_at": entry.observed_at.isoformat(),
        "track": _serialize_track(entry.track),
        "player": _serialize_player(entry.player),
        "time": entry.time,
    }


def _serialize_timer(
    player: Player, timer: ManualTimerState, now: datetime
) -> dict[str, Any]:
    remaining = manual_timer_remaining(timer, now).total_seconds()
    return {
        "player": _serialize_player(player),
        "status": timer.status,
        "started_at": timer.started_at.isoformat() if timer.started_at else None,
        "duration_seconds": timer.duration.total_seconds(),
        "remaining_seconds": max(0.0, remaining),
    }


def _serialize_canonical_game(
    snapshot: CanonicalGameState, now: datetime
) -> dict[str, Any]:
    pending = snapshot.pending
    session = snapshot.session
    pending_payload = {
        "campaign_id": pending.campaign_id,
        "settings": {
            "game_duration_seconds": pending.settings.game_duration.total_seconds(),
            "grace_period_seconds": pending.settings.grace_period.total_seconds(),
            "manual_timer_duration_seconds": pending.settings.manual_timer_duration.total_seconds(),
            "board_seed": pending.settings.board_seed,
        },
    }

    if session is None:
        return {
            "status": "pending",
            "pending": pending_payload,
            "session": None,
        }

    state = session.state
    grace_active = grace_period_active(state, now)
    grace_remaining = (
        max(
            0.0,
            (state.started_at + state.settings.grace_period - now).total_seconds(),
        )
        if grace_active
        else 0.0
    )
    game_remaining = max(
        0.0,
        (state.started_at + state.settings.game_duration - now).total_seconds(),
    )

    if state.board:
        raw_board = state.board
    elif session.tracks:
        grid_tracks = build_bingo_grid(session.tracks, state.settings.board_seed)
        raw_board = tuple(
            tuple(TrackRanking(track, (), None, None) for track in row)
            for row in grid_tracks
        )
    else:
        raw_board = ()

    return {
        "status": state.status,
        "pending": pending_payload,
        "session": {
            "campaign_id": session.campaign_id,
            "started_at": state.started_at.isoformat(),
            "status": state.status,
            "winner": _serialize_player(state.winner),
            "timer_owner": _serialize_player(state.timer_owner),
            "timer_started_at": (
                state.timer_started_at.isoformat() if state.timer_started_at else None
            ),
            "grace_period_active": grace_active,
            "grace_period_remaining_seconds": grace_remaining,
            "game_remaining_seconds": game_remaining,
            "board": [[_serialize_cell(cell) for cell in row] for row in raw_board],
            "records": [_serialize_record(r) for r in session.records],
        },
    }


class ConfigureGameRequest(BaseModel):
    campaign_id: str | None = None
    board_seed: int | None = None
    game_duration_minutes: int | None = None
    grace_period_minutes: int | None = None
    manual_timer_duration_minutes: int | None = None


class StartGameRequest(BaseModel):
    campaign_id: str | None = None
    board_seed: int | None = None
    game_duration_minutes: int | None = None
    grace_period_minutes: int | None = None
    manual_timer_duration_minutes: int | None = None


class TimerActionRequest(BaseModel):
    action: str


@app.get("/api/game", tags=["game"])
def get_game_state() -> dict[str, Any]:
    """Return the current canonical game snapshot."""

    return _serialize_canonical_game(SHARED_CANONICAL_GAME.get(), datetime.now(UTC))


@app.post("/api/game/configure", tags=["game"])
def configure_game(payload: ConfigureGameRequest) -> dict[str, Any]:
    """Update pending setup values before the canonical game starts."""

    snapshot = SHARED_CANONICAL_GAME.get()
    if snapshot.session is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The canonical Bingo game has already started.",
        )

    current_settings = snapshot.pending.settings
    game_duration = (
        timedelta(minutes=payload.game_duration_minutes)
        if payload.game_duration_minutes is not None
        else current_settings.game_duration
    )
    grace_period = (
        timedelta(minutes=payload.grace_period_minutes)
        if payload.grace_period_minutes is not None
        else current_settings.grace_period
    )
    manual_timer_duration = (
        timedelta(minutes=payload.manual_timer_duration_minutes)
        if payload.manual_timer_duration_minutes is not None
        else current_settings.manual_timer_duration
    )
    board_seed = (
        payload.board_seed
        if payload.board_seed is not None
        else current_settings.board_seed
    )

    new_settings = BingoSettings(
        game_duration=game_duration,
        grace_period=grace_period,
        manual_timer_duration=manual_timer_duration,
        board_seed=board_seed,
    )
    campaign_id = (
        payload.campaign_id
        if "campaign_id" in payload.model_fields_set
        else snapshot.pending.campaign_id
    )

    updated = SHARED_CANONICAL_GAME.configure(PendingGame(campaign_id, new_settings))
    return _serialize_canonical_game(updated, datetime.now(UTC))


@app.post("/api/game/start", tags=["game"])
def start_game(payload: StartGameRequest) -> dict[str, Any]:
    """Atomically start the canonical game for all viewers."""

    snapshot = SHARED_CANONICAL_GAME.get()
    campaign_id = payload.campaign_id or snapshot.pending.campaign_id
    if not campaign_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A campaign_id must be selected to start the game.",
        )

    current_settings = snapshot.pending.settings
    settings = BingoSettings(
        game_duration=(
            timedelta(minutes=payload.game_duration_minutes)
            if payload.game_duration_minutes is not None
            else current_settings.game_duration
        ),
        grace_period=(
            timedelta(minutes=payload.grace_period_minutes)
            if payload.grace_period_minutes is not None
            else current_settings.grace_period
        ),
        manual_timer_duration=(
            timedelta(minutes=payload.manual_timer_duration_minutes)
            if payload.manual_timer_duration_minutes is not None
            else current_settings.manual_timer_duration
        ),
        board_seed=(
            payload.board_seed
            if payload.board_seed is not None
            else current_settings.board_seed
        ),
    )

    try:
        token = get_current_service_token()
        updated = start_canonical_game(
            campaign_id,
            token,
            datetime.now(UTC),
            settings=settings,
        )
    except CanonicalGameAlreadyStartedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except UbisoftAuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
    except live_services.LiveServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error

    return _serialize_canonical_game(updated, datetime.now(UTC))


@app.post("/api/game/stop", tags=["game"])
def stop_game() -> dict[str, Any]:
    """Stop the active canonical game."""

    try:
        updated = stop_canonical_game()
    except CanonicalGameNotStartedError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    return _serialize_canonical_game(updated, datetime.now(UTC))


@app.post("/api/game/reset", tags=["game"])
def reset_game() -> dict[str, Any]:
    """Reset the canonical game to pending setup."""

    updated = reset_canonical_game()
    SHARED_MANUAL_TIMER.reset()
    return _serialize_canonical_game(updated, datetime.now(UTC))


@app.post("/api/game/poll", tags=["game"])
def poll_game() -> dict[str, Any]:
    """Poll leaderboards and apply updates to the canonical session."""

    snapshot = SHARED_CANONICAL_GAME.get()
    if snapshot.session is None or snapshot.session.state.status != "active":
        return _serialize_canonical_game(snapshot, datetime.now(UTC))

    try:
        token = get_current_service_token()
        updated = poll_canonical_game(token, datetime.now(UTC))
    except (UbisoftAuthenticationError, live_services.LiveServiceError) as error:
        logger.warning("Poll game failed", extra={"error": str(error)})
        return _serialize_canonical_game(snapshot, datetime.now(UTC))

    return _serialize_canonical_game(updated, datetime.now(UTC))


@app.get("/api/timers", tags=["timers"])
def get_timers() -> list[dict[str, Any]]:
    """Return current states for all configured player timers."""

    now = datetime.now(UTC)
    states = SHARED_MANUAL_TIMER.get_all(now)
    return [
        _serialize_timer(player, states[player.account_id], now) for player in PLAYERS
    ]


@app.post("/api/timers/{account_id}/action", tags=["timers"])
def timer_action(account_id: str, payload: TimerActionRequest) -> dict[str, Any]:
    """Start, stop, or restart a player timer."""

    player = next((p for p in PLAYERS if p.account_id == account_id), None)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player '{account_id}' not found.",
        )

    now = datetime.now(UTC)
    snapshot = SHARED_CANONICAL_GAME.get()
    grace_active = (
        grace_period_active(snapshot.session.state, now)
        if snapshot.session is not None
        else False
    )

    action = payload.action.lower()
    if action == "start":
        timer = SHARED_MANUAL_TIMER.start(player, now, grace_period_active=grace_active)
    elif action == "stop":
        timer = SHARED_MANUAL_TIMER.stop(player)
    elif action == "restart":
        timer = SHARED_MANUAL_TIMER.restart(
            player, now, grace_period_active=grace_active
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported timer action '{payload.action}'. Use start, stop, or restart.",
        )

    return _serialize_timer(player, timer, now)
