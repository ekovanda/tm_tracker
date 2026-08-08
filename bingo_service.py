"""Session-scoped orchestration for the Trackmania bingo game."""

import time
from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass, replace
from datetime import datetime
from threading import Lock

import live_services
from bingo import (
    BingoState,
    ManualTimerState,
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
REQUEST_DELAY_SECONDS = 0.5
ProcessedRecord = dict
TrackLoader = Callable[[str, str], list[Track]]
RecordLoader = Callable[[Track, str], ProcessedRecord]
SleepFn = Callable[[float], None]


class ManualTimerStore:
    """Thread-safe process-wide storage shared by Streamlit viewers."""

    def __init__(self) -> None:
        self._state = ManualTimerState()
        self._lock = Lock()

    def get(self, now: datetime) -> ManualTimerState:
        with self._lock:
            self._state = update_manual_timer(self._state, now)
            return self._state

    def start(self, started_at: datetime) -> ManualTimerState:
        with self._lock:
            self._state = start_manual_timer(self._state, started_at)
            return self._state

    def stop(self) -> ManualTimerState:
        with self._lock:
            self._state = stop_manual_timer(self._state)
            return self._state

    def reset(self) -> ManualTimerState:
        with self._lock:
            self._state = ManualTimerState()
            return self._state


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
class PollSettings:
    """Configurable pacing for the leaderboard requests in one poll."""

    request_delay: float = REQUEST_DELAY_SECONDS
    sleep_fn: SleepFn | None = None


def start_session(
    campaign_id: str,
    jwt_token: str,
    started_at: datetime,
    track_loader: TrackLoader | None = None,
) -> BingoSession:
    """Seed a campaign and create a fresh active session."""

    loader = track_loader or live_services.get_playable_campaign_tracks
    tracks = tuple(loader(campaign_id, jwt_token))
    if len(tracks) != 16:
        raise ValueError("A bingo session requires exactly 16 campaign tracks.")
    return BingoSession(campaign_id, tracks, start_bingo(started_at))


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
    sleeper = settings.sleep_fn or time.sleep
    records = []
    for index, track in enumerate(session.tracks):
        if index:
            sleeper(settings.request_delay)
        records.append(loader(track, jwt_token))
    entries, seen_records = _new_entries(records, now, session.seen_records)
    return replace(
        session,
        state=update_bingo_state(session.state, records, now),
        records=session.records + entries,
        seen_records=seen_records,
    )


def stop_session(session: BingoSession) -> BingoSession:
    """Manually stop the active session."""

    if session.state.status != "active":
        return session
    return replace(session, state=stop_bingo(session.state))


def get_manual_timer(now: datetime) -> ManualTimerState:
    """Read and expire the process-wide manual timer."""

    return SHARED_MANUAL_TIMER.get(now)


def start_manual_timer_for_all(started_at: datetime) -> ManualTimerState:
    """Start the manual timer shared by all viewers of the app process."""

    return SHARED_MANUAL_TIMER.start(started_at)


def stop_manual_timer_for_all() -> ManualTimerState:
    """Stop the manual timer shared by all viewers."""

    return SHARED_MANUAL_TIMER.stop()


def reset_manual_timer_for_all() -> ManualTimerState:
    """Reset the shared manual timer for a new game."""

    return SHARED_MANUAL_TIMER.reset()


def start_session_in_state(
    session_state: MutableMapping[str, object],
    campaign_id: str,
    jwt_token: str,
    started_at: datetime,
    track_loader: TrackLoader | None = None,
) -> BingoSession:
    """Start a session and retain it under the current Streamlit state."""

    session = start_session(campaign_id, jwt_token, started_at, track_loader)
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
