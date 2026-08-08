from datetime import UTC, datetime, timedelta
from itertools import pairwise
from threading import Event, Thread

import pytest

from bingo import BingoSettings
from bingo_service import (
    MAX_REQUESTS_PER_SECOND,
    REQUEST_DELAY_SECONDS,
    SESSION_KEY,
    BingoSession,
    CanonicalGameAlreadyStartedError,
    CanonicalGameNotStartedError,
    CanonicalGameStore,
    ManualTimerStore,
    PendingGame,
    PollingCoordinator,
    PollSettings,
    get_canonical_game_store,
    get_manual_timers,
    poll_session,
    poll_session_in_state,
    reset_canonical_game,
    reset_session,
    restart_manual_timer_for_player,
    start_canonical_game,
    start_session,
    start_session_in_state,
    stop_canonical_game,
    stop_manual_timer_for_player,
    stop_session,
    stop_session_in_state,
)
from live_services import LiveServiceError
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


def test_canonical_game_store_shares_pending_configuration():
    store = CanonicalGameStore()
    pending = PendingGame(
        "campaign",
        BingoSettings(game_duration=timedelta(hours=2), board_seed=7),
    )

    configured = store.configure(pending)

    assert configured == store.get()
    assert configured.pending == pending
    assert configured.session is None


def test_canonical_game_store_is_process_wide_and_fresh_store_is_empty():
    assert get_canonical_game_store() is get_canonical_game_store()
    assert get_canonical_game_store().get().session is None
    assert CanonicalGameStore().get().session is None


def test_canonical_game_store_rejects_invalid_or_conflicting_starts():
    store = CanonicalGameStore()
    stopped_session = stop_session(
        start_session("campaign", "jwt", START, make_loader())
    )

    with pytest.raises(ValueError, match="must start as active"):
        store.start(stopped_session)

    started_session = start_session("campaign", "jwt", START, make_loader())
    store.start(started_session)

    with pytest.raises(CanonicalGameAlreadyStartedError):
        store.start(start_session("campaign", "jwt", START, make_loader()))
    with pytest.raises(CanonicalGameAlreadyStartedError):
        store.configure(PendingGame("other-campaign"))


def test_canonical_lifecycle_helpers_publish_and_clear_shared_game():
    started = start_canonical_game(
        "campaign",
        "jwt",
        START,
        make_loader(),
        BingoSettings(board_seed=5),
    )

    assert started.session is not None
    assert started.session.campaign_id == "campaign"
    assert started.pending.settings.board_seed == 5
    assert get_canonical_game_store().get() is started

    stopped = stop_canonical_game()
    assert stopped.session is not None
    assert stopped.session.state.status == "stopped"

    reset = reset_canonical_game()
    assert reset.session is None
    assert reset.pending.settings.board_seed == 5


def test_canonical_game_store_stops_and_resets_without_losing_pending_config():
    store = CanonicalGameStore()
    pending = PendingGame("campaign", BingoSettings(board_seed=3))
    store.configure(pending)

    with pytest.raises(CanonicalGameNotStartedError):
        store.stop()

    session = start_session("campaign", "jwt", START, make_loader(), pending.settings)
    stopped = store.start(session)
    assert stopped.session is session

    stopped = store.stop()
    assert stopped.session is not None
    assert stopped.session.state.status == "stopped"

    reset = store.reset()
    assert reset.session is None
    assert reset.pending == pending


def test_canonical_game_store_allows_only_one_concurrent_start():
    store = CanonicalGameStore()
    sessions = [
        start_session("campaign", "jwt", START, make_loader()),
        start_session("campaign", "jwt", START, make_loader()),
    ]
    barrier = Event()
    outcomes = []

    def attempt_start(session):
        barrier.wait(timeout=2)
        try:
            outcomes.append(store.start(session))
        except CanonicalGameAlreadyStartedError:
            outcomes.append(None)

    threads = [Thread(target=attempt_start, args=(session,)) for session in sessions]
    for thread in threads:
        thread.start()
    barrier.set()
    for thread in threads:
        thread.join(timeout=2)

    assert len(outcomes) == 2
    assert sum(outcome is not None for outcome in outcomes) == 1
    assert store.get().session in sessions


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


def test_poll_stays_below_two_requests_per_second():
    session = start_session("campaign", "jwt", START, make_loader())
    clock = [0.0]
    request_times = []

    def advance(delay):
        clock[0] += delay

    def load(track, _jwt_token):
        request_times.append(clock[0])
        return make_record_loader()(track, _jwt_token)

    poll_session(
        session,
        "jwt",
        START,
        load,
        PollSettings(REQUEST_DELAY_SECONDS, advance),
    )

    intervals = [current - previous for previous, current in pairwise(request_times)]
    observed_rate = max(1 / interval for interval in intervals)

    assert len(request_times) == len(session.tracks)
    assert all(
        interval == pytest.approx(REQUEST_DELAY_SECONDS) for interval in intervals
    )
    assert observed_rate < MAX_REQUESTS_PER_SECOND


def test_poll_rejects_negative_request_delay():
    session = start_session("campaign", "jwt", START, make_loader())

    with pytest.raises(ValueError, match="cannot be negative"):
        poll_session(
            session,
            "jwt",
            START,
            poll_settings=PollSettings(-0.1, no_sleep),
        )


def test_poll_rejects_request_delay_below_safe_minimum():
    session = start_session("campaign", "jwt", START, make_loader())

    with pytest.raises(ValueError, match="cannot be less than"):
        poll_session(
            session,
            "jwt",
            START,
            poll_settings=PollSettings(REQUEST_DELAY_SECONDS - 0.1, no_sleep),
        )


def test_polling_coordinator_reuses_successful_snapshot():
    clock = [0.0]
    coordinator = PollingCoordinator(lambda: clock[0])
    calls = []
    track = (make_tracks()[0],)

    def load(current_track, token):
        calls.append((current_track, token))
        return {"track": current_track, "players": []}

    first = coordinator.fetch(
        "campaign",
        "NadeoLiveServices",
        "jwt",
        track,
        load,
        request_delay=REQUEST_DELAY_SECONDS,
        sleep_fn=no_sleep,
    )
    second = coordinator.fetch(
        "campaign",
        "NadeoLiveServices",
        "jwt-rotated",
        track,
        load,
        request_delay=REQUEST_DELAY_SECONDS,
        sleep_fn=no_sleep,
    )

    assert first == second
    assert len(calls) == 1
    assert calls[0][1] == "jwt"


def test_polling_coordinator_single_flights_overlapping_refreshes():
    coordinator = PollingCoordinator(lambda: 0.0)
    track = (make_tracks()[0],)
    started = Event()
    release = Event()
    calls = []
    results = []

    def load(current_track, _token):
        calls.append(current_track)
        started.set()
        release.wait(timeout=2)
        return {"track": current_track, "players": []}

    def fetch() -> None:
        results.append(
            coordinator.fetch(
                "campaign",
                "NadeoLiveServices",
                "jwt",
                track,
                load,
                request_delay=REQUEST_DELAY_SECONDS,
                sleep_fn=no_sleep,
                force_refresh=True,
            )
        )

    first = Thread(target=fetch)
    second = Thread(target=fetch)
    first.start()
    assert started.wait(timeout=2)
    second.start()
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert len(calls) == 1
    assert len(results) == 2
    assert results[0] == results[1]


def test_polling_coordinator_accounts_for_request_duration():
    clock = [0.0]
    coordinator = PollingCoordinator(lambda: clock[0])
    request_times = []
    track = tuple(make_tracks()[:2])

    def load(current_track, _token):
        request_times.append(clock[0])
        clock[0] += 0.8
        return {"track": current_track, "players": []}

    coordinator.fetch(
        "campaign",
        "NadeoLiveServices",
        "jwt",
        track,
        load,
        request_delay=REQUEST_DELAY_SECONDS,
        sleep_fn=lambda delay: clock.__setitem__(0, clock[0] + delay),
        force_refresh=True,
    )

    assert request_times == [0.0, 0.8]


def test_polling_coordinator_retries_retryable_errors_with_bounded_backoff():
    coordinator = PollingCoordinator(lambda: 0.0)
    track = (make_tracks()[0],)
    delays = []
    attempts = [0]

    def load(current_track, _token):
        attempts[0] += 1
        if attempts[0] == 1:
            raise LiveServiceError(
                "busy", category="rate_limit", status_code=429, retryable=True
            )
        return {"track": current_track, "players": []}

    result = coordinator.fetch(
        "campaign",
        "NadeoLiveServices",
        "jwt",
        track,
        load,
        request_delay=REQUEST_DELAY_SECONDS,
        sleep_fn=delays.append,
        force_refresh=True,
        backoff_base=2.0,
        backoff_max=2.5,
    )

    assert len(result) == 1
    assert attempts[0] == 2
    assert delays == [2.0, REQUEST_DELAY_SECONDS]


def test_poll_translates_unusable_record_payloads():
    session = start_session("campaign", "jwt", START, make_loader())

    def invalid_loader(_track, _jwt_token):
        raise KeyError("players")

    with pytest.raises(LiveServiceError, match="could not be processed"):
        poll_session(
            session, "jwt", START, invalid_loader, PollSettings(sleep_fn=no_sleep)
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
