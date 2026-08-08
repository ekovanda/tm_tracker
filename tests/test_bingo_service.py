from datetime import UTC, datetime, timedelta

import pytest

from bingo import BingoSettings
from bingo_service import (
    REQUEST_DELAY_SECONDS,
    SESSION_KEY,
    BingoSession,
    ManualTimerStore,
    PollSettings,
    get_manual_timers,
    poll_session,
    poll_session_in_state,
    reset_session,
    restart_manual_timer_for_player,
    start_session,
    start_session_in_state,
    stop_manual_timer_for_player,
    stop_session,
    stop_session_in_state,
)
from player import PLAYERS
from track import Track

START = datetime(2026, 1, 1, tzinfo=UTC)


def no_sleep(_delay: float) -> None:
    pass


def make_tracks():
    numbers = (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19)
    return [Track(f"Track {number}", f"uid-{number}", number) for number in numbers]


def make_loader():
    def load(_campaign_id, _jwt_token):
        return make_tracks()

    return load


def make_record_loader(owner=PLAYERS[1], time=60_000):
    def load(track, _jwt_token):
        return {
            "track": track,
            "players": [
                {"player": owner, "pb": time},
                {"player": PLAYERS[2], "pb": 61_000},
            ],
        }

    return load


def test_start_session_seeds_sixteen_tracks():
    session = start_session("campaign", "jwt", START, make_loader())

    assert isinstance(session, BingoSession)
    assert session.campaign_id == "campaign"
    assert len(session.tracks) == 16
    assert session.state.started_at == START


def test_start_session_preserves_custom_timing_settings():
    settings = BingoSettings(
        game_duration=timedelta(hours=2),
        grace_period=timedelta(minutes=15),
        board_seed=7,
    )

    session = start_session("campaign", "jwt", START, make_loader(), settings)

    assert session.state.settings == settings


def test_start_session_rejects_incomplete_campaign():
    with pytest.raises(ValueError, match="exactly 16"):
        start_session("campaign", "jwt", START, lambda *_: make_tracks()[:-1])


def test_poll_logs_only_new_records_and_updates_bingo_state():
    session = start_session(
        "campaign",
        "jwt",
        START,
        make_loader(),
        BingoSettings(grace_period=timedelta()),
    )
    first = poll_session(
        session,
        "jwt",
        START,
        make_record_loader(),
        PollSettings(sleep_fn=no_sleep),
    )
    duplicate = poll_session(
        first,
        "jwt",
        START + timedelta(minutes=1),
        make_record_loader(),
        PollSettings(sleep_fn=no_sleep),
    )
    changed = poll_session(
        duplicate,
        "jwt",
        START + timedelta(minutes=2),
        make_record_loader(time=59_000),
        PollSettings(sleep_fn=no_sleep),
    )

    assert len(first.records) == 32
    assert len(duplicate.records) == 32
    assert len(changed.records) == 48
    assert first.state.timer_owner is PLAYERS[1]


def test_poll_paces_requests_in_track_order_with_configured_delay():
    session = start_session("campaign", "jwt", START, make_loader())
    loaded_numbers = []
    delays = []

    def load(track, _jwt_token):
        loaded_numbers.append(track.number)
        return make_record_loader()(track, _jwt_token)

    poll_session(
        session,
        "jwt",
        START,
        load,
        PollSettings(REQUEST_DELAY_SECONDS, delays.append),
    )

    assert loaded_numbers == [track.number for track in session.tracks]
    assert delays == [REQUEST_DELAY_SECONDS] * (len(session.tracks) - 1)


def test_poll_rejects_negative_request_delay():
    session = start_session("campaign", "jwt", START, make_loader())

    with pytest.raises(ValueError, match="cannot be negative"):
        poll_session(
            session,
            "jwt",
            START,
            poll_settings=PollSettings(-0.1, no_sleep),
        )


def test_terminal_sessions_are_not_polled_again():
    session = start_session("campaign", "jwt", START, make_loader())
    stopped = stop_session(session)

    assert (
        poll_session(
            stopped, "jwt", START + timedelta(minutes=1), lambda *_: pytest.fail()
        )
        is stopped
    )
    assert stop_session(stopped) is stopped


def test_streamlit_state_start_poll_stop_and_reset():
    state = {}
    started = start_session_in_state(state, "campaign", "jwt", START, make_loader())
    assert state[SESSION_KEY] is started

    polled = poll_session_in_state(
        state,
        "jwt",
        START,
        make_record_loader(),
        PollSettings(sleep_fn=no_sleep),
    )
    assert state[SESSION_KEY] is polled
    stopped = stop_session_in_state(state)
    assert stopped.state.status == "stopped"
    reset_session(state)
    assert SESSION_KEY not in state


def test_state_helpers_require_a_session():
    with pytest.raises(TypeError, match="No active"):
        poll_session_in_state({}, "jwt", START)
    with pytest.raises(TypeError, match="No active"):
        stop_session_in_state({})


def test_manual_timer_store_is_shared_and_expires_from_reads():
    store = ManualTimerStore()
    store.start(PLAYERS[0], START)

    assert store.get(PLAYERS[0], START + timedelta(minutes=1)).status == "active"
    assert store.get(PLAYERS[0], START + timedelta(minutes=10)).status == "expired"
    assert all(timer.status == "ready" for timer in store.reset().values())


def test_manual_timer_store_blocks_start_and_restart_during_grace():
    store = ManualTimerStore()

    assert store.start(PLAYERS[0], START, grace_period_active=True).status == "ready"
    assert store.restart(PLAYERS[0], START, grace_period_active=True).status == "ready"


def test_manual_timer_store_and_shared_helpers_are_independent_per_player():
    store = ManualTimerStore()
    store.start(PLAYERS[0], START)
    restarted = store.restart(PLAYERS[0], START + timedelta(minutes=5))

    assert restarted.status == "active"
    assert restarted.started_at == START + timedelta(minutes=5)
    assert store.get(PLAYERS[0], START).status == "active"
    assert store.get(PLAYERS[1], START).status == "ready"
    assert restart_manual_timer_for_player(PLAYERS[1], START).status == "active"
    assert stop_manual_timer_for_player(PLAYERS[1]).status == "stopped"
    timers = get_manual_timers(START)
    assert timers[PLAYERS[0].account_id].status == "ready"
    assert timers[PLAYERS[1].account_id].status == "stopped"
    assert timers[PLAYERS[2].account_id].status == "ready"
