"""Session-scoped orchestration for the Trackmania bingo game."""

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from threading import Condition, Lock
from typing import Any

import live_services
from authentication import decode_jwt_payload
from bingo import (
    MANUAL_TIMER_DURATION,
    BingoSettings,
    BingoState,
    ManualTimerState,
    restart_manual_timer,
    start_bingo,
    start_manual_timer,
    stop_bingo,
    stop_manual_timer,
    update_bingo_state,
    update_manual_timer,
)
from logger import get_logger
from player import PLAYERS, Player
from tm_lookups import CLUBS
from track import Track

logger = get_logger("bingo_service")

MAX_REQUESTS_PER_SECOND = 2
REQUEST_DELAY_SECONDS = 0.6
POLL_CACHE_TTL_SECONDS = 60.0
MAX_TRANSIENT_RETRIES = 2
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 8.0
ProcessedRecord = dict
TrackLoader = Callable[[str, str], list[Track]]
RecordLoader = Callable[[Track, str], ProcessedRecord]
SleepFn = Callable[[float], None]
ClockFn = Callable[[], float]


class ManualTimerStore:
    """Thread-safe process-wide storage for manual player timers."""

    def __init__(self) -> None:
        self._states = {player.account_id: ManualTimerState() for player in PLAYERS}
        self._lock = Lock()
        self._on_change: Callable[[], None] | None = None

    def set_on_change(self, callback: Callable[[], None] | None) -> None:
        with self._lock:
            self._on_change = callback

    def load_states(self, states: dict[str, ManualTimerState]) -> None:
        with self._lock:
            for account_id, state in states.items():
                if account_id in self._states:
                    self._states[account_id] = state

    def get(self, player: Player, now: datetime) -> ManualTimerState:
        with self._lock:
            state = update_manual_timer(self._states[player.account_id], now)
            self._states[player.account_id] = state
            return state

    def get_all(self, now: datetime) -> dict[str, ManualTimerState]:
        with self._lock:
            for player in PLAYERS:
                self._states[player.account_id] = update_manual_timer(
                    self._states[player.account_id], now
                )
            return self._states.copy()

    def get_raw_states(self) -> dict[str, ManualTimerState]:
        with self._lock:
            return self._states.copy()

    def start(
        self,
        player: Player,
        started_at: datetime,
        grace_period_active: bool = False,
        duration: timedelta = MANUAL_TIMER_DURATION,
    ) -> ManualTimerState:
        with self._lock:
            state = start_manual_timer(
                self._states[player.account_id],
                started_at,
                grace_period_active,
                duration,
            )
            self._states[player.account_id] = state
            cb = self._on_change
        if cb is not None:
            cb()
        return state

    def stop(self, player: Player) -> ManualTimerState:
        with self._lock:
            state = stop_manual_timer(self._states[player.account_id])
            self._states[player.account_id] = state
            cb = self._on_change
        if cb is not None:
            cb()
        return state

    def restart(
        self,
        player: Player,
        started_at: datetime,
        grace_period_active: bool = False,
        duration: timedelta = MANUAL_TIMER_DURATION,
    ) -> ManualTimerState:
        with self._lock:
            state = restart_manual_timer(
                self._states[player.account_id],
                started_at,
                grace_period_active,
                duration,
            )
            self._states[player.account_id] = state
            cb = self._on_change
        if cb is not None:
            cb()
        return state

    def reset(self) -> dict[str, ManualTimerState]:
        with self._lock:
            self._states = {player.account_id: ManualTimerState() for player in PLAYERS}
            copied = self._states.copy()
            cb = self._on_change
        if cb is not None:
            cb()
        return copied


SHARED_MANUAL_TIMER = ManualTimerStore()


@dataclass(frozen=True)
class RecordEntry:
    """A newly observed personal best during the current bingo session."""

    observed_at: datetime
    track: Track
    player: Player
    time: int


@dataclass(frozen=True)
class BingoSession:
    """All mutable game data retained for a bingo session."""

    campaign_id: str
    tracks: tuple[Track, ...]
    state: BingoState
    records: tuple[RecordEntry, ...] = ()
    seen_records: frozenset[tuple[str, str, int]] = frozenset()


@dataclass(frozen=True)
class PendingGame:
    """Shared configuration awaiting the start of the canonical game."""

    campaign_id: str | None = None
    settings: BingoSettings = field(default_factory=BingoSettings)


@dataclass(frozen=True)
class CanonicalGameState:
    """The single pending or started game visible to every viewer."""

    pending: PendingGame = PendingGame()
    session: BingoSession | None = None


class CanonicalGameAlreadyStartedError(RuntimeError):
    """Raised when an operation would replace the current canonical game."""


class CanonicalGameNotStartedError(RuntimeError):
    """Raised when an active canonical game is required but absent."""


class CanonicalGameStore:
    """Thread-safe in-memory boundary for the one canonical Bingo game."""

    def __init__(
        self,
        persistence: Any = None,
        timer_store: ManualTimerStore | None = None,
    ) -> None:
        self._state = CanonicalGameState()
        self._lock = Lock()
        self._persistence = persistence
        self._timer_store = timer_store
        if self._timer_store is not None:
            self._timer_store.set_on_change(self.checkpoint)
        if self._persistence is not None:
            self.rehydrate()

    @property
    def has_persistence(self) -> bool:
        with self._lock:
            return self._persistence is not None

    def set_persistence(
        self,
        persistence: Any,
        timer_store: ManualTimerStore | None = None,
    ) -> None:
        """Configure persistence backend and optional timer store."""

        with self._lock:
            self._persistence = persistence
            if timer_store is not None:
                self._timer_store = timer_store
                self._timer_store.set_on_change(self.checkpoint)

    def checkpoint(self) -> None:
        """Persist current canonical game state and player timers."""

        with self._lock:
            if self._persistence is None:
                return
            current_state = self._state

        timers = None
        if self._timer_store is not None:
            timers = self._timer_store.get_raw_states()
        self._persistence.save_state(current_state, timers)

    def rehydrate(self) -> bool:
        """Rehydrate canonical game and player timers from persistence."""

        with self._lock:
            persistence = self._persistence
        if persistence is None:
            return False

        persisted = persistence.load_state()
        if persisted is None:
            return False

        with self._lock:
            self._state = persisted.canonical_game

        if self._timer_store is not None and persisted.timers:
            self._timer_store.load_states(persisted.timers)

        return persisted.canonical_game.session is not None

    def get(self) -> CanonicalGameState:
        """Return the current immutable game snapshot."""

        with self._lock:
            return self._state

    def configure(self, pending: PendingGame) -> CanonicalGameState:
        """Update pending configuration until the game is started."""

        with self._lock:
            if self._state.session is not None:
                raise CanonicalGameAlreadyStartedError(
                    "The canonical Bingo game has already started."
                )
            self._state = replace(self._state, pending=pending)
            state = self._state
        self.checkpoint()
        return state

    def start(self, session: BingoSession) -> CanonicalGameState:
        """Atomically establish the first active session for all viewers."""

        if session.state.status != "active":
            raise ValueError("The canonical Bingo game must start as active.")
        with self._lock:
            if self._state.session is not None:
                raise CanonicalGameAlreadyStartedError(
                    "The canonical Bingo game has already started."
                )
            self._state = CanonicalGameState(
                PendingGame(session.campaign_id, session.state.settings),
                session,
            )
            state = self._state
        self.checkpoint()
        return state

    def stop(self) -> CanonicalGameState:
        """Stop the canonical game without removing its final state."""

        with self._lock:
            session = self._state.session
            if session is None:
                raise CanonicalGameNotStartedError(
                    "No canonical Bingo game has started."
                )
            self._state = replace(self._state, session=stop_session(session))
            state = self._state
        self.checkpoint()
        return state

    def reset(self) -> CanonicalGameState:
        """Return to pending setup while retaining the shared configuration."""

        with self._lock:
            self._state = replace(self._state, session=None)
            state = self._state
        self.checkpoint()
        return state

    def update_session(
        self, updater: Callable[[BingoSession], BingoSession]
    ) -> CanonicalGameState:
        """Atomically apply one transition to the current canonical session."""

        with self._lock:
            session = self._state.session
            if session is None:
                raise CanonicalGameNotStartedError(
                    "No canonical Bingo game has started."
                )
            self._state = replace(self._state, session=updater(session))
            state = self._state
        self.checkpoint()
        return state


SHARED_CANONICAL_GAME = CanonicalGameStore(timer_store=SHARED_MANUAL_TIMER)


def get_canonical_game_store() -> CanonicalGameStore:
    """Return the process-wide canonical game store for all viewers."""

    return SHARED_CANONICAL_GAME


@dataclass(frozen=True)
class PollSnapshot:
    """Successful raw leaderboard records shared across viewers."""

    records: tuple[ProcessedRecord, ...]
    completed_at: float


class PollingCoordinator:
    """Coordinate and pace leaderboard polls across the application process."""

    # pylint: disable=too-many-arguments,too-many-locals
    def __init__(
        self, clock: ClockFn | None = None, aggregate_pacing: bool = True
    ) -> None:
        self._clock = clock or time.monotonic
        self._aggregate_pacing = aggregate_pacing
        self._condition = Condition()
        self._cache: dict[tuple[str, str, int | None], PollSnapshot] = {}
        self._in_flight: set[tuple[str, str, int | None]] = set()
        self._next_request_at = 0.0
        self._request_count = 0

    def fetch(
        self,
        campaign_id: str,
        token_audience: str,
        jwt_token: str,
        tracks: tuple[Track, ...],
        loader: RecordLoader,
        *,
        request_delay: float,
        sleep_fn: SleepFn,
        cache_ttl: float = POLL_CACHE_TTL_SECONDS,
        force_refresh: bool = False,
        loader_key: int | None = None,
        max_retries: int = MAX_TRANSIENT_RETRIES,
        backoff_base: float = BACKOFF_BASE_SECONDS,
        backoff_max: float = BACKOFF_MAX_SECONDS,
    ) -> tuple[ProcessedRecord, ...]:
        key = (campaign_id, token_audience, loader_key)
        with self._condition:
            if not force_refresh:
                cached = self._cache.get(key)
                if cached and self._clock() - cached.completed_at < cache_ttl:
                    logger.debug(
                        "Leaderboard records served from snapshot cache",
                        extra={"campaign_id": campaign_id},
                    )
                    return cached.records
            while key in self._in_flight:
                self._condition.wait()
                cached = self._cache.get(key)
                if cached:
                    logger.debug(
                        "Leaderboard records served from in-flight wait",
                        extra={"campaign_id": campaign_id},
                    )
                    return cached.records
            self._in_flight.add(key)

        logger.info(
            "Polling leaderboard records for campaign",
            extra={"campaign_id": campaign_id, "track_count": len(tracks)},
        )
        try:
            records = tuple(
                self._fetch_records(
                    tracks,
                    loader,
                    jwt_token,
                    request_delay,
                    sleep_fn,
                    max_retries,
                    backoff_base,
                    backoff_max,
                )
            )
        except Exception:
            with self._condition:
                self._in_flight.remove(key)
                self._condition.notify_all()
            raise

        with self._condition:
            self._cache[key] = PollSnapshot(records, self._clock())
            self._in_flight.remove(key)
            self._condition.notify_all()
        return records

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def _fetch_records(
        self,
        tracks: tuple[Track, ...],
        loader: RecordLoader,
        jwt_token: str,
        request_delay: float,
        sleep_fn: SleepFn,
        max_retries: int,
        backoff_base: float,
        backoff_max: float,
    ) -> list[ProcessedRecord]:
        records = []
        for track in tracks:
            for attempt in range(max_retries + 1):
                self._wait_for_request_slot(request_delay, sleep_fn)
                try:
                    records.append(loader(track, jwt_token))
                    break
                except live_services.LiveServiceError as error:
                    if not error.retryable or attempt == max_retries:
                        raise
                    delay = error.retry_after or min(
                        backoff_base * (2**attempt), backoff_max
                    )
                    logger.warning(
                        "Retryable LiveServiceError during track poll, backing off",
                        extra={
                            "track": track.uid,
                            "attempt": attempt + 1,
                            "delay": delay,
                            "category": error.category,
                            "status_code": error.status_code,
                        },
                    )
                    sleep_fn(delay)
        return records

    def _wait_for_request_slot(self, request_delay: float, sleep_fn: SleepFn) -> None:
        if not self._aggregate_pacing:
            if self._request_count:
                sleep_fn(request_delay)
            self._request_count += 1
            return
        with self._condition:
            now = self._clock()
            wait_for = max(0.0, self._next_request_at - now)
            self._next_request_at = max(now, self._next_request_at) + request_delay
        if wait_for:
            sleep_fn(wait_for)


SHARED_POLLING_COORDINATOR = PollingCoordinator()


@dataclass(frozen=True)
class PollSettings:
    """Configurable pacing for the leaderboard requests in one poll."""

    request_delay: float = REQUEST_DELAY_SECONDS
    sleep_fn: SleepFn | None = None
    cache_ttl: float = POLL_CACHE_TTL_SECONDS
    force_refresh: bool = False
    coordinator: PollingCoordinator | None = None


def start_session(
    campaign_id: str,
    jwt_token: str,
    started_at: datetime,
    track_loader: TrackLoader | None = None,
    settings: BingoSettings | None = None,
) -> BingoSession:
    """Seed a campaign and create a fresh active session."""

    loader = track_loader or live_services.get_playable_campaign_tracks
    tracks = tuple(loader(campaign_id, jwt_token))
    if len(tracks) != 16:
        raise ValueError("A bingo session requires exactly 16 campaign tracks.")
    return BingoSession(campaign_id, tracks, start_bingo(started_at, settings))


def start_canonical_game(
    campaign_id: str,
    jwt_token: str,
    started_at: datetime,
    track_loader: TrackLoader | None = None,
    settings: BingoSettings | None = None,
) -> CanonicalGameState:
    """Load and atomically publish the one active game for all viewers."""

    logger.info("Starting canonical Bingo game", extra={"campaign_id": campaign_id})
    session = start_session(campaign_id, jwt_token, started_at, track_loader, settings)
    return SHARED_CANONICAL_GAME.start(session)


def stop_canonical_game() -> CanonicalGameState:
    """Stop the shared game while retaining its final snapshot."""

    logger.info("Stopping canonical Bingo game")
    return SHARED_CANONICAL_GAME.stop()


def reset_canonical_game() -> CanonicalGameState:
    """Return the shared game to pending setup."""

    logger.info("Resetting canonical Bingo game to pending setup")
    return SHARED_CANONICAL_GAME.reset()


def _live_record_loader(track: Track, jwt_token: str) -> ProcessedRecord:
    raw_record = live_services.get_club_track_pbs(
        CLUBS["Elliot"], track, jwt_token=jwt_token
    )
    return live_services.postprocess_club_track_pbs(raw_record, tracks=[track])


def _new_entries(
    records: Iterable[ProcessedRecord],
    observed_at: datetime,
    seen_records: frozenset[tuple[str, str, int]],
) -> tuple[tuple[RecordEntry, ...], frozenset[tuple[str, str, int]]]:
    entries: list[RecordEntry] = []
    updated_seen = set(seen_records)
    configured_players = {player.account_id: player for player in PLAYERS}

    for record in records:
        track = record["track"]
        for result in record.get("players", []):
            player = result.get("player")
            record_time = result.get("pb")
            if (
                player is None
                or record_time is None
                or player.account_id not in configured_players
            ):
                continue
            key = (track.uid, player.account_id, record_time)
            if key in updated_seen:
                continue
            updated_seen.add(key)
            logger.info(
                "Observed new personal best",
                extra={
                    "track": track.name,
                    "player": player.name,
                    "time": record_time,
                },
            )
            entries.append(
                RecordEntry(
                    observed_at,
                    track,
                    configured_players[player.account_id],
                    record_time,
                )
            )

    return tuple(entries), frozenset(updated_seen)


def _fetch_records(
    session: BingoSession,
    jwt_token: str,
    record_loader: RecordLoader | None,
    poll_settings: PollSettings | None,
) -> tuple[ProcessedRecord, ...]:
    loader = record_loader or _live_record_loader
    settings = poll_settings or PollSettings()
    if settings.request_delay < 0:
        raise ValueError("The leaderboard request delay cannot be negative.")
    if settings.request_delay < REQUEST_DELAY_SECONDS:
        raise ValueError(
            f"The leaderboard request delay cannot be less than "
            f"{REQUEST_DELAY_SECONDS} seconds."
        )
    sleeper = settings.sleep_fn or time.sleep
    coordinator = settings.coordinator or (
        SHARED_POLLING_COORDINATOR
        if record_loader is None
        else PollingCoordinator(aggregate_pacing=False)
    )
    return coordinator.fetch(
        session.campaign_id,
        _token_audience(jwt_token),
        jwt_token,
        session.tracks,
        lambda track, token: _load_record(loader, track, token),
        request_delay=settings.request_delay,
        sleep_fn=sleeper,
        cache_ttl=settings.cache_ttl,
        force_refresh=settings.force_refresh or record_loader is not None,
        loader_key=None if record_loader is None else id(loader),
    )


def _apply_records(
    session: BingoSession,
    records: tuple[ProcessedRecord, ...],
    now: datetime,
) -> BingoSession:
    entries, seen_records = _new_entries(records, now, session.seen_records)
    return replace(
        session,
        state=update_bingo_state(session.state, records, now),
        records=session.records + entries,
        seen_records=seen_records,
    )


def poll_session(
    session: BingoSession,
    jwt_token: str,
    now: datetime,
    record_loader: RecordLoader | None = None,
    poll_settings: PollSettings | None = None,
) -> BingoSession:
    """Poll all campaign tracks once and apply the resulting bingo transition."""

    if session.state.status != "active":
        return session

    records = _fetch_records(session, jwt_token, record_loader, poll_settings)
    return _apply_records(session, records, now)


def poll_canonical_game(
    jwt_token: str,
    now: datetime,
    record_loader: RecordLoader | None = None,
    poll_settings: PollSettings | None = None,
) -> CanonicalGameState:
    """Poll and update the one canonical game visible to every viewer."""

    store = SHARED_CANONICAL_GAME
    snapshot = store.get()
    session = snapshot.session
    if session is None:
        raise CanonicalGameNotStartedError("No canonical Bingo game has started.")
    if session.state.status != "active":
        return snapshot

    records = _fetch_records(session, jwt_token, record_loader, poll_settings)

    def apply_if_same_game(current: BingoSession) -> BingoSession:
        if (
            current.campaign_id != session.campaign_id
            or current.state.started_at != session.state.started_at
        ):
            return current
        return _apply_records(current, records, now)

    return store.update_session(apply_if_same_game)


def _load_record(loader: RecordLoader, track: Track, jwt_token: str) -> ProcessedRecord:
    try:
        return loader(track, jwt_token)
    except (KeyError, TypeError, ValueError) as error:
        raise live_services.LiveServiceError(
            "Leaderboard payload could not be processed.", category="payload"
        ) from error


def _token_audience(jwt_token: str) -> str:
    try:
        audience = decode_jwt_payload(jwt_token).get("aud")
    except (ValueError, KeyError, TypeError):
        audience = None
    return str(audience or "unknown")


def stop_session(session: BingoSession) -> BingoSession:
    """Manually stop the active session."""

    if session.state.status != "active":
        return session
    return replace(session, state=stop_bingo(session.state))


def get_manual_timers(now: datetime) -> dict[str, ManualTimerState]:
    """Read and expire all process-wide player timers."""

    return SHARED_MANUAL_TIMER.get_all(now)


def start_manual_timer_for_player(
    player: Player,
    started_at: datetime,
    grace_period_active: bool = False,
    duration: timedelta = MANUAL_TIMER_DURATION,
) -> ManualTimerState:
    """Start one player's timer for every viewer of the app process."""

    return SHARED_MANUAL_TIMER.start(player, started_at, grace_period_active, duration)


def stop_manual_timer_for_player(player: Player) -> ManualTimerState:
    """Stop one player's timer for every viewer of the app process."""

    return SHARED_MANUAL_TIMER.stop(player)


def stop_manual_timers() -> dict[str, ManualTimerState]:
    """Stop every player's timer when the Bingo session ends."""

    return {
        player.account_id: stop_manual_timer_for_player(player) for player in PLAYERS
    }


def restart_manual_timer_for_player(
    player: Player,
    started_at: datetime,
    grace_period_active: bool = False,
    duration: timedelta = MANUAL_TIMER_DURATION,
) -> ManualTimerState:
    """Restart one player's timer from ten minutes for every viewer."""

    return SHARED_MANUAL_TIMER.restart(
        player, started_at, grace_period_active, duration
    )


def reset_manual_timers() -> dict[str, ManualTimerState]:
    """Reset every player's timer for a new game."""

    return SHARED_MANUAL_TIMER.reset()
