"""Session-scoped orchestration for the Trackmania bingo game."""

import time
from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from threading import Condition, Lock

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
from player import PLAYERS, Player
from tm_lookups import CLUBS
from track import Track

SESSION_KEY = "bingo_session"
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
    """Thread-safe process-wide storage shared by Streamlit viewers."""

    def __init__(self) -> None:
        self._states = {player.account_id: ManualTimerState() for player in PLAYERS}
        self._lock = Lock()

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
            return state

    def stop(self, player: Player) -> ManualTimerState:
        with self._lock:
            state = stop_manual_timer(self._states[player.account_id])
            self._states[player.account_id] = state
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
            return state

    def reset(self) -> dict[str, ManualTimerState]:
        with self._lock:
            self._states = {player.account_id: ManualTimerState() for player in PLAYERS}
            return self._states.copy()


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
    """All mutable game data retained in Streamlit session state."""

    campaign_id: str
    tracks: tuple[Track, ...]
    state: BingoState
    records: tuple[RecordEntry, ...] = ()
    seen_records: frozenset[tuple[str, str, int]] = frozenset()


@dataclass(frozen=True)
class PollSnapshot:
    """Successful raw leaderboard records shared between Streamlit viewers."""

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
                    return cached.records
            while key in self._in_flight:
                self._condition.wait()
                cached = self._cache.get(key)
                if cached:
                    return cached.records
            self._in_flight.add(key)

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
            entries.append(
                RecordEntry(
                    observed_at,
                    track,
                    configured_players[player.account_id],
                    record_time,
                )
            )

    return tuple(entries), frozenset(updated_seen)


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
    records = coordinator.fetch(
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
    entries, seen_records = _new_entries(records, now, session.seen_records)
    return replace(
        session,
        state=update_bingo_state(session.state, records, now),
        records=session.records + entries,
        seen_records=seen_records,
    )


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


# pylint: disable=too-many-arguments,too-many-positional-arguments
def start_session_in_state(
    session_state: MutableMapping[str, object],
    campaign_id: str,
    jwt_token: str,
    started_at: datetime,
    track_loader: TrackLoader | None = None,
    settings: BingoSettings | None = None,
) -> BingoSession:
    """Start a session and retain it under the current Streamlit state."""

    session = start_session(campaign_id, jwt_token, started_at, track_loader, settings)
    session_state[SESSION_KEY] = session
    return session


def poll_session_in_state(
    session_state: MutableMapping[str, object],
    jwt_token: str,
    now: datetime,
    record_loader: RecordLoader | None = None,
    poll_settings: PollSettings | None = None,
) -> BingoSession:
    """Poll the session held by Streamlit and store its updated snapshot."""

    session = session_state.get(SESSION_KEY)
    if not isinstance(session, BingoSession):
        raise TypeError("No active bingo session exists.")
    updated = poll_session(
        session,
        jwt_token,
        now,
        record_loader,
        poll_settings,
    )
    session_state[SESSION_KEY] = updated
    return updated


def stop_session_in_state(session_state: MutableMapping[str, object]) -> BingoSession:
    """Stop and retain the current session snapshot."""

    session = session_state.get(SESSION_KEY)
    if not isinstance(session, BingoSession):
        raise TypeError("No active bingo session exists.")
    stopped = stop_session(session)
    session_state[SESSION_KEY] = stopped
    return stopped


def reset_session(session_state: MutableMapping[str, object]) -> None:
    """Remove the current session so a new campaign can be started."""

    session_state.pop(SESSION_KEY, None)
