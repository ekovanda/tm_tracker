"""FastAPI service entrypoint for Trackmania Bingo."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import Lock
from typing import Any, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

import live_services
from authentication import (
    PasswordConfigurationError,
    UbisoftAuthenticationError,
    create_session_token,
    ensure_nadeo_service_token,
    get_nadeo_service_token,
    verify_app_password,
    verify_session_token,
)
from bingo import (
    PLAYABLE_TRACK_NUMBERS,
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
        return version("tm-bingo")
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


BACKGROUND_POLL_INTERVAL_SECONDS = 60.0
BACKGROUND_POLL_CHECK_INTERVAL_SECONDS = 5.0
_POLL_STATE: dict[str, datetime | None] = {"last_polled_at": None}


def get_last_poll_time() -> datetime | None:
    """Return the timestamp of the most recent leaderboard poll."""
    return _POLL_STATE["last_polled_at"]


def set_last_poll_time(timestamp: datetime | None) -> None:
    """Update or clear the timestamp of the most recent leaderboard poll."""
    _POLL_STATE["last_polled_at"] = timestamp


def poll_is_due(
    last_polled_at: datetime | None,
    now: datetime,
    interval_seconds: float = BACKGROUND_POLL_INTERVAL_SECONDS,
) -> bool:
    """Return whether the leaderboard poll interval has elapsed."""
    if last_polled_at is None:
        return True
    return (now - last_polled_at).total_seconds() >= interval_seconds


async def run_background_poll_once(
    now: datetime | None = None,
    interval_seconds: float = BACKGROUND_POLL_INTERVAL_SECONDS,
) -> bool:
    """Execute a single leaderboard poll if a game session is currently active and due."""
    current_time = now or datetime.now(UTC)
    snapshot = SHARED_CANONICAL_GAME.get()
    if snapshot.session is None or snapshot.session.state.status != "active":
        return False

    if not poll_is_due(get_last_poll_time(), current_time, interval_seconds):
        return False

    try:
        token = await asyncio.to_thread(get_current_service_token)
        await asyncio.to_thread(poll_canonical_game, token, current_time)
        set_last_poll_time(current_time)
        logger.info(
            "Background leaderboard poll completed successfully",
            extra={"polled_at": current_time.isoformat()},
        )
        return True
    except (
        UbisoftAuthenticationError,
        live_services.LiveServiceError,
        RuntimeError,
        OSError,
    ) as error:
        logger.warning(
            "Background leaderboard poll failed",
            extra={"error": str(error)},
        )
        set_last_poll_time(current_time)
        return False


async def background_polling_loop(
    check_interval_seconds: float = BACKGROUND_POLL_CHECK_INTERVAL_SECONDS,
    poll_interval_seconds: float = BACKGROUND_POLL_INTERVAL_SECONDS,
) -> None:
    """Periodically monitor the canonical game session and trigger leaderboard polls when due."""
    logger.info("Starting background leaderboard poller loop")
    try:
        while True:
            await asyncio.sleep(check_interval_seconds)
            await run_background_poll_once(interval_seconds=poll_interval_seconds)
    except asyncio.CancelledError:
        logger.info("Background leaderboard poller loop cancelled")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Lifespan context manager ensuring storage is initialized and poller runs."""

    if not SHARED_CANONICAL_GAME.has_persistence:
        init_storage()
    else:
        SHARED_CANONICAL_GAME.rehydrate()

    poller_task = asyncio.create_task(background_polling_loop())
    try:
        yield
    finally:
        poller_task.cancel()
        with suppress(asyncio.CancelledError):
            await poller_task


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

STATIC_DIR = Path(__file__).resolve().parent / "static"


class SPAStaticFiles(StaticFiles):
    """Static file handler providing SPA fallback to index.html for unmapped frontend routes."""

    async def get_response(self, path: str, scope: Any) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as ex:
            if ex.status_code == status.HTTP_404_NOT_FOUND and not path.startswith(
                "api"
            ):
                return await super().get_response("index.html", scope)
            raise


if STATIC_DIR.is_dir():
    app.mount(
        "/static", StaticFiles(directory=str(STATIC_DIR), html=True), name="static"
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
    token: str | None = None


class CampaignResponse(BaseModel):
    campaign_id: str
    name: str


def require_auth(authorization: str | None = Header(None)) -> str:
    """Validate Bearer session token on protected endpoints."""

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme. Use 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    if not verify_session_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token


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
    token = create_session_token("tm_bingo_user")
    return VerifyPasswordResponse(authenticated=True, token=token)


@app.get(
    "/api/campaigns",
    response_model=list[CampaignResponse],
    dependencies=[Depends(require_auth)],
    tags=["campaigns"],
)
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
    return {
        "account_id": player.account_id,
        "name": player.name,
        "alias": getattr(player, "alias", player.name),
    }


def _serialize_track(track: Track) -> dict[str, Any]:
    series = (track.number - 1) // 5 if track.number is not None else 0
    return {
        "uid": track.uid,
        "name": track.name,
        "number": track.number,
        "track_number": track.number,
        "series": series,
    }


def _serialize_cell(cell: Any) -> dict[str, Any]:
    winning_time = (
        cell.rankings[0].time if (cell.owner is not None and cell.rankings) else None
    )
    return {
        "track": _serialize_track(cell.track),
        "rankings": [
            {"player": _serialize_player(r.player), "time": r.time}
            for r in cell.rankings
        ],
        "owner": _serialize_player(cell.owner),
        "winning_time": winning_time,
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


def _compute_player_medals(
    board: Any,
) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    medal_counts: dict[str, dict[str, int]] = {}
    rank_points: dict[str, int] = {}
    for p in PLAYERS:
        counts = {"gold": 0, "silver": 0, "bronze": 0, "unfinished": 0}
        for row in board:
            for cell in row:
                rankings: list[Any] = list(getattr(cell, "rankings", ()))
                if len(rankings) > 0 and rankings[0].player.account_id == p.account_id:
                    counts["gold"] += 1
                elif (
                    len(rankings) > 1 and rankings[1].player.account_id == p.account_id
                ):
                    counts["silver"] += 1
                elif (
                    len(rankings) > 2 and rankings[2].player.account_id == p.account_id
                ):
                    counts["bronze"] += 1
                else:
                    counts["unfinished"] += 1
        medal_counts[p.account_id] = counts
        rank_points[p.account_id] = (
            1 * counts["gold"]
            + 2 * counts["silver"]
            + 3 * counts["bronze"]
            + 5 * counts["unfinished"]
        )
    return medal_counts, rank_points


_CAMPAIGN_TRACKS_CACHE: dict[str, list[Track]] = {}


def get_preview_tracks(campaign_id: str | None = None) -> list[Track]:
    """Return campaign tracks for board preview using cache or default playable tracks."""
    if campaign_id and campaign_id in _CAMPAIGN_TRACKS_CACHE:
        return _CAMPAIGN_TRACKS_CACHE[campaign_id]

    if campaign_id:
        try:
            token = get_current_service_token()
            tracks = live_services.get_playable_campaign_tracks(campaign_id, token)
            _CAMPAIGN_TRACKS_CACHE[campaign_id] = tracks
            return tracks
        except (UbisoftAuthenticationError, live_services.LiveServiceError) as error:
            logger.debug(
                "Live services unavailable for preview tracks",
                extra={"error": str(error), "campaign_id": campaign_id},
            )

    return [
        Track(name=f"Track {number:02d}", uid=f"track-{number:02d}", number=number)
        for number in PLAYABLE_TRACK_NUMBERS
    ]


def _compute_preview_board(
    campaign_id: str | None, board_seed: int
) -> list[list[dict[str, Any]]]:
    tracks = get_preview_tracks(campaign_id)
    grid = build_bingo_grid(tracks, board_seed)
    return [
        [
            {
                "track": _serialize_track(track),
                "rankings": [],
                "owner": None,
                "winning_time": None,
                "margin": None,
            }
            for track in row
        ]
        for row in grid
    ]


def _serialize_canonical_game(
    snapshot: CanonicalGameState, now: datetime
) -> dict[str, Any]:
    pending = snapshot.pending
    session = snapshot.session
    preview_board = _compute_preview_board(
        pending.campaign_id, pending.settings.board_seed
    )
    pending_payload = {
        "campaign_id": pending.campaign_id,
        "settings": {
            "game_duration_seconds": pending.settings.game_duration.total_seconds(),
            "grace_period_seconds": pending.settings.grace_period.total_seconds(),
            "manual_timer_duration_seconds": pending.settings.manual_timer_duration.total_seconds(),
            "board_seed": pending.settings.board_seed,
        },
        "board": preview_board,
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

    medal_counts, rank_points = _compute_player_medals(raw_board)
    last_polled = get_last_poll_time()

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
            "medal_counts": medal_counts,
            "rank_points": rank_points,
            "last_polled_at": (
                last_polled.isoformat() if last_polled is not None else None
            ),
        },
    }


class ConfigureGameRequest(BaseModel):
    campaign_id: str | None = None
    board_seed: int | None = None
    game_duration_minutes: int | None = None
    game_duration_seconds: int | None = None
    grace_period_minutes: int | None = None
    grace_period_seconds: int | None = None
    manual_timer_duration_minutes: int | None = None
    manual_timer_duration_seconds: int | None = None


class StartGameRequest(BaseModel):
    campaign_id: str | None = None
    board_seed: int | None = None
    game_duration_minutes: int | None = None
    game_duration_seconds: int | None = None
    grace_period_minutes: int | None = None
    grace_period_seconds: int | None = None
    manual_timer_duration_minutes: int | None = None
    manual_timer_duration_seconds: int | None = None


class TimerActionRequest(BaseModel):
    action: str


@app.get("/api/game", tags=["game"])
def get_game_state() -> dict[str, Any]:
    """Return the current canonical game snapshot."""

    return _serialize_canonical_game(SHARED_CANONICAL_GAME.get(), datetime.now(UTC))


@app.post("/api/game/configure", dependencies=[Depends(require_auth)], tags=["game"])
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
        timedelta(seconds=payload.game_duration_seconds)
        if payload.game_duration_seconds is not None
        else (
            timedelta(minutes=payload.game_duration_minutes)
            if payload.game_duration_minutes is not None
            else current_settings.game_duration
        )
    )
    grace_period = (
        timedelta(seconds=payload.grace_period_seconds)
        if payload.grace_period_seconds is not None
        else (
            timedelta(minutes=payload.grace_period_minutes)
            if payload.grace_period_minutes is not None
            else current_settings.grace_period
        )
    )
    manual_timer_duration = (
        timedelta(seconds=payload.manual_timer_duration_seconds)
        if payload.manual_timer_duration_seconds is not None
        else (
            timedelta(minutes=payload.manual_timer_duration_minutes)
            if payload.manual_timer_duration_minutes is not None
            else current_settings.manual_timer_duration
        )
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


@app.post("/api/game/start", dependencies=[Depends(require_auth)], tags=["game"])
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
    game_duration = (
        timedelta(seconds=payload.game_duration_seconds)
        if payload.game_duration_seconds is not None
        else (
            timedelta(minutes=payload.game_duration_minutes)
            if payload.game_duration_minutes is not None
            else current_settings.game_duration
        )
    )
    grace_period = (
        timedelta(seconds=payload.grace_period_seconds)
        if payload.grace_period_seconds is not None
        else (
            timedelta(minutes=payload.grace_period_minutes)
            if payload.grace_period_minutes is not None
            else current_settings.grace_period
        )
    )
    manual_timer_duration = (
        timedelta(seconds=payload.manual_timer_duration_seconds)
        if payload.manual_timer_duration_seconds is not None
        else (
            timedelta(minutes=payload.manual_timer_duration_minutes)
            if payload.manual_timer_duration_minutes is not None
            else current_settings.manual_timer_duration
        )
    )
    settings = BingoSettings(
        game_duration=game_duration,
        grace_period=grace_period,
        manual_timer_duration=manual_timer_duration,
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
        if updated.session and updated.session.tracks:
            _CAMPAIGN_TRACKS_CACHE[campaign_id] = list(updated.session.tracks)
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

    now = datetime.now(UTC)
    set_last_poll_time(now)
    return _serialize_canonical_game(updated, now)


@app.post("/api/game/stop", dependencies=[Depends(require_auth)], tags=["game"])
def stop_game() -> dict[str, Any]:
    """Stop the active canonical game."""

    try:
        updated = stop_canonical_game()
    except CanonicalGameNotStartedError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    set_last_poll_time(None)
    return _serialize_canonical_game(updated, datetime.now(UTC))


@app.post("/api/game/reset", dependencies=[Depends(require_auth)], tags=["game"])
def reset_game() -> dict[str, Any]:
    """Reset the canonical game to pending setup."""

    updated = reset_canonical_game()
    SHARED_MANUAL_TIMER.reset()
    set_last_poll_time(None)
    return _serialize_canonical_game(updated, datetime.now(UTC))


@app.post("/api/game/poll", dependencies=[Depends(require_auth)], tags=["game"])
def poll_game() -> dict[str, Any]:
    """Poll leaderboards and apply updates to the canonical session."""

    now = datetime.now(UTC)
    snapshot = SHARED_CANONICAL_GAME.get()
    if snapshot.session is None or snapshot.session.state.status != "active":
        return _serialize_canonical_game(snapshot, now)

    try:
        token = get_current_service_token()
        updated = poll_canonical_game(token, now)
        set_last_poll_time(now)
    except (UbisoftAuthenticationError, live_services.LiveServiceError) as error:
        logger.warning("Poll game failed", extra={"error": str(error)})
        return _serialize_canonical_game(snapshot, now)

    return _serialize_canonical_game(updated, now)


@app.get("/api/timers", tags=["timers"])
def get_timers() -> list[dict[str, Any]]:
    """Return current states for all configured player timers."""

    now = datetime.now(UTC)
    states = SHARED_MANUAL_TIMER.get_all(now)
    return [
        _serialize_timer(player, states[player.account_id], now) for player in PLAYERS
    ]


@app.post(
    "/api/timers/{account_id}/action",
    dependencies=[Depends(require_auth)],
    tags=["timers"],
)
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


if STATIC_DIR.is_dir():
    app.mount(
        "/",
        SPAStaticFiles(directory=str(STATIC_DIR), html=True),
        name="frontend_root",
    )
