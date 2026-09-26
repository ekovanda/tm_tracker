"""Storage and persistence layer for Trackmania Bingo game state."""

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

from bingo import (
    BingoSettings,
    BingoState,
    ManualTimerState,
    PlayerTime,
    TrackRanking,
)
from bingo_service import (
    BingoSession,
    CanonicalGameState,
    PendingGame,
    RecordEntry,
)
from logger import get_logger
from player import PLAYERS, Player
from track import Track

logger = get_logger("storage")

PLAYERS_BY_ID: dict[str, Player] = {player.account_id: player for player in PLAYERS}


@dataclass(frozen=True)
class PersistedState:
    """Rehydrated canonical game state and player timers."""

    canonical_game: CanonicalGameState
    timers: dict[str, ManualTimerState] = field(default_factory=dict)


def _serialize_player(player: Player | None) -> dict[str, Any] | None:
    if player is None:
        return None
    return {
        "account_id": player.account_id,
        "name": player.name,
        "alias": getattr(player, "alias", player.name),
    }


def _deserialize_player(data: dict[str, Any] | None) -> Player | None:
    if not data:
        return None
    account_id = str(data["account_id"])
    if account_id in PLAYERS_BY_ID:
        return PLAYERS_BY_ID[account_id]
    return Player(
        name=str(data.get("name", "Unknown")),
        account_id=account_id,
        alias=str(data.get("alias", data.get("name", "Unknown"))),
    )


def _serialize_track(track: Track) -> dict[str, Any]:
    return {
        "uid": track.uid,
        "name": track.name,
        "number": track.number,
    }


def _deserialize_track(data: dict[str, Any]) -> Track:
    return Track(
        name=str(data["name"]),
        uid=str(data["uid"]),
        number=data.get("number"),
    )


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return None


def _serialize_session(session: BingoSession) -> dict[str, Any]:
    state = session.state
    board_payload: list[dict[str, Any]] = []
    for row in state.board:
        row_payload = []
        for cell in row:
            cell_payload = {
                "track": _serialize_track(cell.track),
                "rankings": [
                    {
                        "player": _serialize_player(pt.player),
                        "time": pt.time,
                    }
                    for pt in cell.rankings
                ],
                "owner": _serialize_player(cell.owner),
                "margin": cell.margin,
            }
            row_payload.append(cell_payload)
        board_payload.append({"cells": row_payload})

    records_payload = [
        {
            "observed_at": entry.observed_at.isoformat(),
            "track": _serialize_track(entry.track),
            "player": _serialize_player(entry.player),
            "time": entry.time,
        }
        for entry in session.records
    ]

    seen_records_payload = [
        {"track_uid": str(item[0]), "player_id": str(item[1]), "time": int(item[2])}
        for item in session.seen_records
    ]

    return {
        "campaign_id": session.campaign_id,
        "tracks": [_serialize_track(t) for t in session.tracks],
        "state": {
            "started_at": state.started_at.isoformat(),
            "status": state.status,
            "winner": _serialize_player(state.winner),
            "timer_owner": _serialize_player(state.timer_owner),
            "timer_started_at": (
                state.timer_started_at.isoformat() if state.timer_started_at else None
            ),
            "settings": {
                "game_duration_seconds": state.settings.game_duration.total_seconds(),
                "grace_period_seconds": state.settings.grace_period.total_seconds(),
                "manual_timer_duration_seconds": (
                    state.settings.manual_timer_duration.total_seconds()
                ),
                "board_seed": state.settings.board_seed,
                "auto_line_timers": state.settings.auto_line_timers,
            },
            "board": board_payload,
        },
        "records": records_payload,
        "seen_records": seen_records_payload,
    }


def serialize_game_state(
    game_state: CanonicalGameState,
    timers: dict[str, ManualTimerState] | None = None,
) -> dict[str, Any]:
    """Serialize CanonicalGameState and optional manual timers to a dictionary."""

    pending = game_state.pending
    pending_payload: dict[str, Any] = {
        "campaign_id": pending.campaign_id,
        "settings": {
            "game_duration_seconds": pending.settings.game_duration.total_seconds(),
            "grace_period_seconds": pending.settings.grace_period.total_seconds(),
            "manual_timer_duration_seconds": (
                pending.settings.manual_timer_duration.total_seconds()
            ),
            "board_seed": pending.settings.board_seed,
            "auto_line_timers": pending.settings.auto_line_timers,
        },
    }

    session = game_state.session
    session_payload = _serialize_session(session) if session is not None else None

    timers_payload: dict[str, Any] = {}
    if timers:
        for account_id, timer_state in timers.items():
            timers_payload[account_id] = {
                "status": timer_state.status,
                "started_at": (
                    timer_state.started_at.isoformat()
                    if timer_state.started_at
                    else None
                ),
                "duration_seconds": timer_state.duration.total_seconds(),
            }

    return {
        "pending": pending_payload,
        "session": session_payload,
        "timers": timers_payload,
        "saved_at": datetime.now(UTC).isoformat(),
    }


def _deserialize_session(session_data: dict[str, Any]) -> BingoSession:
    # pylint: disable=too-many-locals
    campaign_id = str(session_data["campaign_id"])
    tracks = tuple(
        _deserialize_track(t_data) for t_data in session_data.get("tracks", ())
    )

    state_data = session_data["state"]
    started_at = _parse_datetime(state_data["started_at"])
    if started_at is None:
        raise ValueError("Session state missing valid started_at timestamp.")

    timer_started_at = _parse_datetime(state_data.get("timer_started_at"))
    status = str(state_data.get("status", "active"))
    winner = _deserialize_player(state_data.get("winner"))
    timer_owner = _deserialize_player(state_data.get("timer_owner"))

    state_settings_data = state_data.get("settings", {})
    state_settings = BingoSettings(
        game_duration=timedelta(
            seconds=state_settings_data.get("game_duration_seconds", 18000.0)
        ),
        grace_period=timedelta(
            seconds=state_settings_data.get("grace_period_seconds", 1800.0)
        ),
        manual_timer_duration=timedelta(
            seconds=state_settings_data.get("manual_timer_duration_seconds", 600.0)
        ),
        board_seed=int(state_settings_data.get("board_seed", 0)),
        auto_line_timers=bool(state_settings_data.get("auto_line_timers", False)),
    )

    board_rows: list[tuple[TrackRanking, ...]] = []
    raw_board = state_data.get("board", ())
    if isinstance(raw_board, dict) and "rows" in raw_board:
        raw_rows = raw_board["rows"]
    else:
        raw_rows = raw_board

    for row_entry in raw_rows:
        if isinstance(row_entry, dict) and "cells" in row_entry:
            row_data = row_entry["cells"]
        else:
            row_data = row_entry
        cell_list: list[TrackRanking] = []
        for cell_data in row_data:
            cell_track = _deserialize_track(cell_data["track"])
            rankings = tuple(
                PlayerTime(
                    player=_deserialize_player(pt["player"]) or PLAYERS[0],
                    time=int(pt["time"]),
                )
                for pt in cell_data.get("rankings", ())
            )
            owner = _deserialize_player(cell_data.get("owner"))
            margin = (
                int(cell_data["margin"])
                if cell_data.get("margin") is not None
                else None
            )
            cell_list.append(TrackRanking(cell_track, rankings, owner, margin))
        board_rows.append(tuple(cell_list))

    bingo_state = BingoState(
        started_at=started_at,
        settings=state_settings,
        status=status,
        board=tuple(board_rows),
        timer_owner=timer_owner,
        timer_started_at=timer_started_at,
        winner=winner,
    )

    records = tuple(
        RecordEntry(
            observed_at=_parse_datetime(r_data["observed_at"]) or started_at,
            track=_deserialize_track(r_data["track"]),
            player=_deserialize_player(r_data["player"]) or PLAYERS[0],
            time=int(r_data["time"]),
        )
        for r_data in session_data.get("records", ())
    )

    seen_records_raw = session_data.get("seen_records", ())
    seen_records_list = []
    for item in seen_records_raw:
        if isinstance(item, dict):
            seen_records_list.append(
                (str(item["track_uid"]), str(item["player_id"]), int(item["time"]))
            )
        else:
            seen_records_list.append((str(item[0]), str(item[1]), int(item[2])))
    seen_records = frozenset(seen_records_list)

    return BingoSession(
        campaign_id=campaign_id,
        tracks=tracks,
        state=bingo_state,
        records=records,
        seen_records=seen_records,
    )


def deserialize_game_state(data: dict[str, Any]) -> PersistedState:
    """Deserialize a dictionary into a PersistedState instance."""

    pending_data = data.get("pending", {})
    pending_settings_data = pending_data.get("settings", {})
    pending_settings = BingoSettings(
        game_duration=timedelta(
            seconds=pending_settings_data.get("game_duration_seconds", 18000.0)
        ),
        grace_period=timedelta(
            seconds=pending_settings_data.get("grace_period_seconds", 1800.0)
        ),
        manual_timer_duration=timedelta(
            seconds=pending_settings_data.get("manual_timer_duration_seconds", 600.0)
        ),
        board_seed=int(pending_settings_data.get("board_seed", 0)),
        auto_line_timers=bool(pending_settings_data.get("auto_line_timers", False)),
    )
    pending = PendingGame(
        campaign_id=pending_data.get("campaign_id"),
        settings=pending_settings,
    )

    session_data = data.get("session")
    session = _deserialize_session(session_data) if session_data is not None else None

    timers: dict[str, ManualTimerState] = {}
    timers_data = data.get("timers", {})
    for account_id, timer_data in timers_data.items():
        timer_started_at = _parse_datetime(timer_data.get("started_at"))
        timer_status = str(timer_data.get("status", "ready"))
        duration = timedelta(seconds=timer_data.get("duration_seconds", 600.0))
        timers[account_id] = ManualTimerState(
            status=timer_status,
            started_at=timer_started_at,
            duration=duration,
        )

    return PersistedState(
        canonical_game=CanonicalGameState(pending=pending, session=session),
        timers=timers,
    )


class GameStatePersistence(ABC):
    """Abstract interface for persisting and rehydrating Bingo game state."""

    @abstractmethod
    def save_state(
        self,
        game_state: CanonicalGameState,
        timers: dict[str, ManualTimerState] | None = None,
    ) -> None:
        """Persist the canonical game state and player timers."""

    @abstractmethod
    def load_state(self) -> PersistedState | None:
        """Load persisted state, returning None if no state is stored."""

    @abstractmethod
    def clear_state(self) -> None:
        """Clear or delete any persisted state."""


class InMemoryGameStateStore(GameStatePersistence):
    """Thread-safe in-memory store for local development and testing."""

    def __init__(self) -> None:
        self._data: dict[str, Any] | None = None
        self._lock = Lock()

    def save_state(
        self,
        game_state: CanonicalGameState,
        timers: dict[str, ManualTimerState] | None = None,
    ) -> None:
        with self._lock:
            self._data = serialize_game_state(game_state, timers)

    def load_state(self) -> PersistedState | None:
        with self._lock:
            if self._data is None:
                return None
            return deserialize_game_state(deepcopy(self._data))

    def clear_state(self) -> None:
        with self._lock:
            self._data = None


class FirestoreGameStateStore(GameStatePersistence):
    """GCP Firestore implementation with graceful in-memory fallback."""

    def __init__(
        self,
        client: Any = None,
        collection_name: str = "bingo_state",
        document_id: str = "canonical_game",
        fallback_to_memory: bool = True,
    ) -> None:
        self._collection_name = collection_name
        self._document_id = document_id
        self._fallback_to_memory = fallback_to_memory
        self._fallback_store: InMemoryGameStateStore | None = None
        self._memory_backup = InMemoryGameStateStore()
        self._consecutive_failures = 0
        self._client = client

        if self._client is None:
            try:
                # Late import to prevent hard dependency crashes if env differs
                from google.cloud import (  # pylint: disable=import-outside-toplevel
                    firestore,
                )

                self._client = firestore.Client()
                logger.info(
                    "Initialized Firestore client for collection=%s, document=%s",
                    collection_name,
                    document_id,
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                if self._fallback_to_memory:
                    logger.warning(
                        "Firestore client unavailable (%s); using in-memory store",
                        exc,
                    )
                    self._fallback_store = InMemoryGameStateStore()
                else:
                    raise

    @property
    def is_using_fallback(self) -> bool:
        return self._fallback_store is not None or self._consecutive_failures > 0

    def save_state(
        self,
        game_state: CanonicalGameState,
        timers: dict[str, ManualTimerState] | None = None,
    ) -> None:
        if self._fallback_store is not None:
            self._fallback_store.save_state(game_state, timers)
            return

        payload = serialize_game_state(game_state, timers)
        try:
            doc_ref = self._client.collection(self._collection_name).document(
                self._document_id
            )
            doc_ref.set(payload)
            self._consecutive_failures = 0
            self._memory_backup.save_state(game_state, timers)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if self._fallback_to_memory:
                self._consecutive_failures += 1
                logger.warning(
                    "Firestore write failed (%s); saved to in-memory backup (failures=%d)",
                    exc,
                    self._consecutive_failures,
                )
                self._memory_backup.save_state(game_state, timers)
            else:
                raise

    def load_state(self) -> PersistedState | None:
        if self._fallback_store is not None:
            return self._fallback_store.load_state()

        try:
            doc_ref = self._client.collection(self._collection_name).document(
                self._document_id
            )
            snapshot = doc_ref.get()
            self._consecutive_failures = 0
            if not snapshot.exists:
                self._memory_backup.clear_state()
                return None
            data = snapshot.to_dict()
            if not data:
                return None
            persisted = deserialize_game_state(data)
            if persisted:
                self._memory_backup.save_state(
                    persisted.canonical_game, persisted.timers
                )
            return persisted
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if self._fallback_to_memory:
                self._consecutive_failures += 1
                logger.warning(
                    "Firestore read failed (%s); loading from in-memory backup (failures=%d)",
                    exc,
                    self._consecutive_failures,
                )
                return self._memory_backup.load_state()
            raise

    def clear_state(self) -> None:
        if self._fallback_store is not None:
            self._fallback_store.clear_state()
            return

        try:
            doc_ref = self._client.collection(self._collection_name).document(
                self._document_id
            )
            doc_ref.delete()
            self._consecutive_failures = 0
            self._memory_backup.clear_state()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if self._fallback_to_memory:
                self._consecutive_failures += 1
                logger.warning(
                    "Firestore delete failed (%s); cleared in-memory backup (failures=%d)",
                    exc,
                    self._consecutive_failures,
                )
                self._memory_backup.clear_state()
            else:
                raise


def create_game_state_store(
    collection_name: str = "bingo_state",
    document_id: str = "canonical_game",
    fallback_to_memory: bool = True,
) -> GameStatePersistence:
    """Factory creating the configured game state persistence backend."""

    return FirestoreGameStateStore(
        collection_name=collection_name,
        document_id=document_id,
        fallback_to_memory=fallback_to_memory,
    )
