"""Tests for storage and persistence module."""

from dataclasses import replace as dc_replace
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

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
    CanonicalGameStore,
    ManualTimerStore,
    PendingGame,
    RecordEntry,
)
from player import PLAYERS
from storage import (
    FirestoreGameStateStore,
    InMemoryGameStateStore,
    _deserialize_player,
    _deserialize_track,
    _parse_datetime,
    _serialize_player,
    _serialize_track,
    create_game_state_store,
    deserialize_game_state,
    serialize_game_state,
)
from track import Track


def _sample_tracks() -> tuple[Track, ...]:
    return tuple(
        Track(f"Track {i}", f"uid-{i}", number=i)
        for i in (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19)
    )


def _sample_board(tracks: tuple[Track, ...]) -> tuple[tuple[TrackRanking, ...], ...]:
    rows = []
    track_iter = iter(tracks)
    for _ in range(4):
        row = []
        for _ in range(4):
            t = next(track_iter)
            rankings = (
                PlayerTime(PLAYERS[0], 45000),
                PlayerTime(PLAYERS[1], 46000),
            )
            row.append(TrackRanking(t, rankings, PLAYERS[0], 1000))
        rows.append(tuple(row))
    return tuple(rows)


def test_serialize_deserialize_pending_only():
    settings = BingoSettings(
        game_duration=timedelta(hours=4),
        grace_period=timedelta(minutes=20),
        manual_timer_duration=timedelta(minutes=8),
        board_seed=42,
    )
    pending = PendingGame(campaign_id="camp-123", settings=settings)
    game_state = CanonicalGameState(pending=pending, session=None)

    data = serialize_game_state(game_state)
    persisted = deserialize_game_state(data)

    assert persisted.canonical_game.session is None
    assert persisted.canonical_game.pending.campaign_id == "camp-123"
    assert persisted.canonical_game.pending.settings.game_duration == timedelta(hours=4)
    assert persisted.canonical_game.pending.settings.grace_period == timedelta(
        minutes=20
    )
    assert persisted.canonical_game.pending.settings.manual_timer_duration == timedelta(
        minutes=8
    )
    assert persisted.canonical_game.pending.settings.board_seed == 42
    assert not persisted.timers


def test_serialize_deserialize_active_session_and_timers():
    now = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
    tracks = _sample_tracks()
    board = _sample_board(tracks)

    settings = BingoSettings(
        game_duration=timedelta(hours=5),
        grace_period=timedelta(minutes=30),
        manual_timer_duration=timedelta(minutes=10),
        board_seed=99,
    )
    state = BingoState(
        started_at=now,
        settings=settings,
        status="active",
        board=board,
        timer_owner=PLAYERS[1],
        timer_started_at=now + timedelta(minutes=5),
        winner=PLAYERS[0],
    )

    records = (
        RecordEntry(
            observed_at=now + timedelta(minutes=2),
            track=tracks[0],
            player=PLAYERS[0],
            time=45000,
        ),
    )
    seen_records = frozenset([(tracks[0].uid, PLAYERS[0].account_id, 45000)])

    session = BingoSession(
        campaign_id="camp-456",
        tracks=tracks,
        state=state,
        records=records,
        seen_records=seen_records,
    )
    game_state = CanonicalGameState(
        pending=PendingGame(campaign_id="camp-456", settings=settings),
        session=session,
    )

    timers = {
        PLAYERS[0].account_id: ManualTimerState(
            status="running",
            started_at=now,
            duration=timedelta(minutes=10),
        ),
        PLAYERS[1].account_id: ManualTimerState(
            status="ready",
            started_at=None,
            duration=timedelta(minutes=10),
        ),
    }

    payload = serialize_game_state(game_state, timers)
    persisted = deserialize_game_state(payload)

    assert persisted.canonical_game.session is not None
    restored_session = persisted.canonical_game.session
    assert restored_session.campaign_id == "camp-456"
    assert len(restored_session.tracks) == 16
    assert restored_session.tracks[0].uid == tracks[0].uid
    assert restored_session.state.started_at == now
    assert restored_session.state.status == "active"
    assert restored_session.state.winner == PLAYERS[0]
    assert restored_session.state.timer_owner == PLAYERS[1]
    assert restored_session.state.timer_started_at == now + timedelta(minutes=5)
    assert restored_session.state.settings.board_seed == 99

    # Check board cell rankings
    first_cell = restored_session.state.board[0][0]
    assert first_cell.track.uid == tracks[0].uid
    assert first_cell.owner == PLAYERS[0]
    assert first_cell.margin == 1000
    assert len(first_cell.rankings) == 2
    assert first_cell.rankings[0].player == PLAYERS[0]
    assert first_cell.rankings[0].time == 45000

    # Records
    assert len(restored_session.records) == 1
    assert restored_session.records[0].time == 45000
    assert restored_session.records[0].player == PLAYERS[0]
    assert (
        tracks[0].uid,
        PLAYERS[0].account_id,
        45000,
    ) in restored_session.seen_records

    # Timers
    assert len(persisted.timers) == 2
    assert persisted.timers[PLAYERS[0].account_id].status == "running"
    assert persisted.timers[PLAYERS[0].account_id].started_at == now
    assert persisted.timers[PLAYERS[1].account_id].status == "ready"


def test_deserialize_player_and_track_helpers():
    assert _serialize_player(None) is None
    assert _deserialize_player(None) is None

    # Known player
    p_data = _serialize_player(PLAYERS[0])
    restored = _deserialize_player(p_data)
    assert restored is PLAYERS[0]

    # Unknown custom player
    custom_data = {"account_id": "custom-uuid", "name": "Custom", "alias": "Cust"}
    custom_player = _deserialize_player(custom_data)
    assert custom_player is not None
    assert custom_player.account_id == "custom-uuid"
    assert custom_player.name == "Custom"
    assert custom_player.alias == "Cust"

    # Track
    t = Track("T1", "u1", 1)
    t_data = _serialize_track(t)
    restored_t = _deserialize_track(t_data)
    assert restored_t.name == "T1"
    assert restored_t.uid == "u1"
    assert restored_t.number == 1


def test_parse_datetime_helper():
    now = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
    assert _parse_datetime(None) is None
    assert _parse_datetime(now) == now
    assert _parse_datetime(now.isoformat()) == now
    assert _parse_datetime(12345) is None


def test_in_memory_store_lifecycle():
    store = InMemoryGameStateStore()
    assert store.load_state() is None

    game_state = CanonicalGameState(pending=PendingGame(campaign_id="test-camp"))
    store.save_state(game_state)

    loaded = store.load_state()
    assert loaded is not None
    assert loaded.canonical_game.pending.campaign_id == "test-camp"

    store.clear_state()
    assert store.load_state() is None


def test_firestore_store_with_mock_client():
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value = mock_collection
    mock_collection.document.return_value = mock_doc

    store = FirestoreGameStateStore(
        client=mock_client,
        collection_name="test_col",
        document_id="test_doc",
    )
    assert not store.is_using_fallback

    # Test save
    game_state = CanonicalGameState(pending=PendingGame(campaign_id="camp-x"))
    store.save_state(game_state)
    mock_client.collection.assert_called_with("test_col")
    mock_collection.document.assert_called_with("test_doc")
    mock_doc.set.assert_called_once()
    payload = mock_doc.set.call_args[0][0]
    assert payload["pending"]["campaign_id"] == "camp-x"

    # Test load when exists
    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    mock_snapshot.to_dict.return_value = payload
    mock_doc.get.return_value = mock_snapshot

    loaded = store.load_state()
    assert loaded is not None
    assert loaded.canonical_game.pending.campaign_id == "camp-x"

    # Test load when not exists
    mock_snapshot.exists = False
    assert store.load_state() is None

    # Test clear
    store.clear_state()
    mock_doc.delete.assert_called_once()


def test_firestore_store_fallback_on_init():
    with patch(
        "google.cloud.firestore.Client", side_effect=Exception("No credentials")
    ):
        # Fallback enabled (default)
        store = FirestoreGameStateStore(fallback_to_memory=True)
        assert store.is_using_fallback

        game_state = CanonicalGameState(
            pending=PendingGame(campaign_id="fallback-camp")
        )
        store.save_state(game_state)
        loaded = store.load_state()
        assert loaded is not None
        assert loaded.canonical_game.pending.campaign_id == "fallback-camp"

        store.clear_state()
        assert store.load_state() is None

        # Fallback disabled raises
        with pytest.raises(Exception, match="No credentials"):
            FirestoreGameStateStore(fallback_to_memory=False)


def test_firestore_store_fallback_on_runtime_errors():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_doc

    # Save fails -> switches to fallback
    mock_doc.set.side_effect = Exception("Write error")
    store = FirestoreGameStateStore(client=mock_client, fallback_to_memory=True)
    game_state = CanonicalGameState(pending=PendingGame(campaign_id="camp-error"))
    store.save_state(game_state)
    assert store.is_using_fallback
    assert store.load_state() is not None
    assert store.load_state().canonical_game.pending.campaign_id == "camp-error"

    # Read error without fallback
    mock_client_no_fb = MagicMock()
    mock_client_no_fb.collection.return_value.document.return_value.get.side_effect = (
        Exception("Read error")
    )
    store_no_fb = FirestoreGameStateStore(
        client=mock_client_no_fb, fallback_to_memory=False
    )
    with pytest.raises(Exception, match="Read error"):
        store_no_fb.load_state()

    # Clear error without fallback
    mock_client_no_fb.collection.return_value.document.return_value.delete.side_effect = Exception(
        "Delete error"
    )
    with pytest.raises(Exception, match="Delete error"):
        store_no_fb.clear_state()


def test_deserialize_invalid_session_started_at():
    data = {
        "session": {
            "campaign_id": "c1",
            "tracks": [],
            "state": {"started_at": None},
        }
    }
    with pytest.raises(ValueError, match="missing valid started_at"):
        deserialize_game_state(data)


def test_firestore_store_edge_cases():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_doc

    # Snapshot to_dict returns empty
    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    mock_snapshot.to_dict.return_value = {}
    mock_doc.get.return_value = mock_snapshot
    store = FirestoreGameStateStore(client=mock_client)
    assert store.load_state() is None

    # Read error with fallback
    mock_doc.get.side_effect = Exception("Read failed")
    assert store.load_state() is None
    assert store.is_using_fallback

    # Clear error with fallback
    store_clear_fb = FirestoreGameStateStore(
        client=mock_client, fallback_to_memory=True
    )
    mock_doc.delete.side_effect = Exception("Delete failed")
    store_clear_fb.clear_state()
    assert store_clear_fb.is_using_fallback


def test_create_game_state_store_factory():
    with patch("google.cloud.firestore.Client") as mock_init:
        mock_init.return_value = MagicMock()
        store = create_game_state_store()
        assert isinstance(store, FirestoreGameStateStore)
        assert not store.is_using_fallback

    with patch("google.cloud.firestore.Client", side_effect=Exception("No creds")):
        store_fb = create_game_state_store()
        assert isinstance(store_fb, FirestoreGameStateStore)
        assert store_fb.is_using_fallback


def test_canonical_game_store_checkpoint_and_rehydration():
    persistence = InMemoryGameStateStore()
    timer_store = ManualTimerStore()
    game_store = CanonicalGameStore(
        persistence=persistence,
        timer_store=timer_store,
    )
    assert game_store.has_persistence

    # 1. Configure checkpoints pending
    pending = PendingGame(campaign_id="camp-rehydrate")
    game_store.configure(pending)
    saved = persistence.load_state()
    assert saved is not None
    assert saved.canonical_game.pending.campaign_id == "camp-rehydrate"

    # 2. Start checkpoints session
    now = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    tracks = _sample_tracks()
    board = _sample_board(tracks)
    session = BingoSession(
        campaign_id="camp-rehydrate",
        tracks=tracks,
        state=BingoState(started_at=now, status="active", board=board),
    )
    game_store.start(session)
    saved = persistence.load_state()
    assert saved is not None
    assert saved.canonical_game.session is not None
    assert saved.canonical_game.session.campaign_id == "camp-rehydrate"

    # 3. Timer toggle checkpoints timer state
    timer_store.start(PLAYERS[0], started_at=now)
    saved = persistence.load_state()
    assert saved is not None
    assert saved.timers[PLAYERS[0].account_id].status == "active"

    # 4. Update session (personal best or line completion) checkpoints transition
    def add_winner(s: BingoSession) -> BingoSession:
        return dc_replace(s, state=dc_replace(s.state, winner=PLAYERS[0]))

    game_store.update_session(add_winner)
    saved = persistence.load_state()
    assert saved is not None
    assert saved.canonical_game.session.state.winner == PLAYERS[0]

    # 5. Stop checkpoints stopped state
    game_store.stop()
    saved = persistence.load_state()
    assert saved is not None
    assert saved.canonical_game.session.state.status == "stopped"

    # 6. Rehydration on a new CanonicalGameStore instance (simulating server restart)
    new_timer_store = ManualTimerStore()
    new_game_store = CanonicalGameStore(
        persistence=persistence,
        timer_store=new_timer_store,
    )
    # The new store automatically rehydrates upon initialization
    assert new_game_store.get().session is not None
    assert new_game_store.get().session.campaign_id == "camp-rehydrate"
    assert new_game_store.get().session.state.winner == PLAYERS[0]
    assert new_game_store.get().session.state.status == "stopped"
    assert new_timer_store.get(PLAYERS[0], now).status == "active"

    # 7. Reset clears in-flight session and checkpoints clean/pending
    new_game_store.reset()
    saved_reset = persistence.load_state()
    assert saved_reset is not None
    assert saved_reset.canonical_game.session is None

    # Rehydrating after reset returns False (no active session)
    fresh_store = CanonicalGameStore(persistence=persistence)
    assert not fresh_store.rehydrate()
    assert fresh_store.get().session is None
