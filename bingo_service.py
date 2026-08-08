"""Session-scoped orchestration for the Trackmania bingo game."""

from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass, replace
from datetime import datetime

import live_services
from bingo import BingoState, start_bingo, stop_bingo, update_bingo_state
from player import PLAYERS, Player
from tm_lookups import CLUBS
from track import Track

SESSION_KEY = "bingo_session"
ProcessedRecord = dict
TrackLoader = Callable[[str, str], list[Track]]
RecordLoader = Callable[[Track, str], ProcessedRecord]


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
    return live_services.postprocess_club_track_pbs(raw_record)


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
            time = result.get("pb")
            if (
                player is None
                or time is None
                or player.account_id not in configured_players
            ):
                continue
            key = (track.uid, player.account_id, time)
            if key in updated_seen:
                continue
            updated_seen.add(key)
            entries.append(
                RecordEntry(
                    observed_at, track, configured_players[player.account_id], time
                )
            )

    return tuple(entries), frozenset(updated_seen)


def poll_session(
    session: BingoSession,
    jwt_token: str,
    now: datetime,
    record_loader: RecordLoader | None = None,
) -> BingoSession:
    """Poll all campaign tracks once and apply the resulting bingo transition."""

    if session.state.status != "active":
        return session

    loader = record_loader or _live_record_loader
    records = tuple(loader(track, jwt_token) for track in session.tracks)
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
) -> BingoSession:
    """Poll the session held by Streamlit and store its updated snapshot."""

    session = session_state.get(SESSION_KEY)
    if not isinstance(session, BingoSession):
        raise TypeError("No active bingo session exists.")
    updated = poll_session(session, jwt_token, now, record_loader)
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
