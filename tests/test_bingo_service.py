from datetime import UTC, datetime, timedelta

import pytest

from bingo_service import (
    REQUEST_DELAY_SECONDS,
    SESSION_KEY,
    BingoSession,
    PollSettings,
    poll_session,
    poll_session_in_state,
    reset_session,
    start_session,
    start_session_in_state,
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
    return lambda campaign_id, jwt_token: make_tracks()


def make_record_loader(owner=PLAYERS[1], time=60_000):
    def load(track, jwt_token):
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


def test_start_session_rejects_incomplete_campaign():
    with pytest.raises(ValueError, match="exactly 16"):
        start_session("campaign", "jwt", START, lambda *_: make_tracks()[:-1])


def test_poll_logs_only_new_records_and_updates_bingo_state():
    session = start_session("campaign", "jwt", START, make_loader())
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
