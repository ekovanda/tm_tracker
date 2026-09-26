from datetime import UTC, datetime, timedelta

import pytest

from bingo import (
    GAME_DURATION,
    GRACE_PERIOD,
    MANUAL_TIMER_DURATION,
    BingoSettings,
    ManualTimerState,
    build_bingo_grid,
    grace_period_active,
    manual_timer_remaining,
    rank_track,
    restart_manual_timer,
    start_bingo,
    start_manual_timer,
    stop_bingo,
    stop_manual_timer,
    update_bingo_state,
    update_manual_timer,
)
from player import PLAYERS
from track import Track


def make_tracks():
    numbers = (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19)
    return [Track(f"Track {number}", f"uid-{number}", number) for number in numbers]


def make_records(owner_by_number=None, missing_numbers=()):
    owner_by_number = owner_by_number or {}
    records = []
    for number in (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19):
        if number in missing_numbers:
            continue
        track = Track(f"Track {number}", f"uid-{number}", number)
        owner = owner_by_number.get(number, PLAYERS[1])
        players = [
            {"player": owner, "pb": 60_000},
            {"player": PLAYERS[2], "pb": 61_000},
        ]
        records.append({"track": track, "players": players})
    return records


def test_grid_has_one_track_from_each_batch_in_each_row_and_column():
    grid = build_bingo_grid(make_tracks())
    assert len(grid) == 4
    assert all(len(row) == 4 for row in grid)

    def batch(number):
        return (number - 1) // 5

    assert all({batch(track.number) for track in row} == {0, 1, 2, 3} for row in grid)
    assert all(
        {batch(grid[row][column].number) for row in range(4)} == {0, 1, 2, 3}
        for column in range(4)
    )


def test_grid_has_unique_playable_tracks_and_expected_arrangement():
    grid = build_bingo_grid(make_tracks())
    numbers = [track.number for row in grid for track in row]

    assert len(numbers) == len(set(numbers)) == 16
    assert not set(numbers) & {5, 10, 15, 20}
    assert [[track.number for track in row] for row in grid] == [
        [1, 8, 11, 18],
        [7, 14, 17, 4],
        [13, 16, 3, 6],
        [19, 2, 9, 12],
    ]


@pytest.mark.parametrize("board_seed", (0, 1, 2))
def test_each_board_seed_is_deterministic_and_balanced(board_seed):
    first = build_bingo_grid(make_tracks(), board_seed)
    second = build_bingo_grid(make_tracks(), board_seed)

    assert [[track.number for track in row] for row in first] == [
        [track.number for track in row] for row in second
    ]
    numbers = [track.number for row in first for track in row]
    assert len(numbers) == len(set(numbers)) == 16
    assert all(
        {(track.number - 1) // 5 for track in row} == {0, 1, 2, 3} for row in first
    )
    assert all(
        {(first[row][column].number - 1) // 5 for row in range(4)} == {0, 1, 2, 3}
        for column in range(4)
    )


def test_state_transition_uses_persisted_board_seed():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    state = start_bingo(
        start,
        BingoSettings(grace_period=timedelta(), board_seed=1),
    )

    updated = update_bingo_state(state, make_records(), start)

    assert [[ranking.track.number for ranking in row] for row in updated.board] == [
        [4, 6, 11, 16],
        [7, 14, 19, 2],
        [12, 18, 3, 9],
        [17, 1, 8, 13],
    ]


def test_grid_requires_sixteen_tracks():
    with pytest.raises(ValueError, match="exactly 16"):
        build_bingo_grid(make_tracks()[:-1])

    duplicate_tracks = make_tracks()
    duplicate_tracks[-1] = duplicate_tracks[0]
    with pytest.raises(ValueError, match="distinct"):
        build_bingo_grid(duplicate_tracks)


def test_grid_rejects_non_playable_track_numbers():
    tracks = make_tracks()
    tracks[-1] = Track("Track 5", "uid-5", 5)

    with pytest.raises(ValueError, match="playable"):
        build_bingo_grid(tracks)


def test_ranking_handles_missing_times_and_ties():
    track = Track("Track 1", "uid-1", 1)
    ranking = rank_track(
        track,
        [{"player": PLAYERS[0], "pb": None}, {"player": PLAYERS[1], "pb": 60_000}],
    )
    assert ranking.owner is PLAYERS[1]
    assert ranking.margin is None

    tie = rank_track(
        track,
        [{"player": PLAYERS[0], "pb": 60_000}, {"player": PLAYERS[1], "pb": 60_000}],
    )
    assert tie.owner is None
    assert tie.margin is None


def test_ownership_and_timer_reset_when_line_owner_changes():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    all_numbers = (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19)
    # Start from an alternating baseline where no player holds a line
    baseline_owners = {
        number: PLAYERS[i % len(PLAYERS)] for i, number in enumerate(all_numbers)
    }

    # Give Player 1 Row 0 (1, 8, 11, 18)
    p1_owners = dict(baseline_owners)
    for n in (1, 8, 11, 18):
        p1_owners[n] = PLAYERS[1]

    first = start_bingo(
        start, BingoSettings(grace_period=timedelta(), auto_line_timers=True)
    )
    first_update = update_bingo_state(
        first, make_records(p1_owners), start + timedelta(minutes=1)
    )
    assert first_update.timer_owner is PLAYERS[1]
    assert first_update.timer_started_at == start + timedelta(minutes=1)

    # Break Player 1's Row 0 and give Player 0 Row 1 (7, 14, 17, 4)
    p0_owners = dict(p1_owners)
    p0_owners[1] = PLAYERS[2]  # Break Player 1's line
    for n in (7, 14, 17, 4):
        p0_owners[n] = PLAYERS[0]  # Complete Player 0's line

    changed = update_bingo_state(
        first_update,
        make_records(p0_owners),
        start + timedelta(minutes=2),
    )
    assert changed.timer_owner is PLAYERS[0]
    assert changed.timer_started_at == start + timedelta(minutes=2)


def test_stable_line_completes_after_ten_minutes():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    settings = BingoSettings(grace_period=timedelta(), auto_line_timers=True)
    state = update_bingo_state(start_bingo(start, settings), make_records(), start)
    completed = update_bingo_state(state, make_records(), start + timedelta(minutes=10))
    assert completed.status == "completed"
    assert completed.winner is PLAYERS[1]


def test_auto_line_timers_disabled_by_default():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    settings = BingoSettings(grace_period=timedelta())
    assert settings.auto_line_timers is False
    state = update_bingo_state(start_bingo(start, settings), make_records(), start)
    assert state.timer_owner is None
    assert state.timer_started_at is None
    after_ten = update_bingo_state(state, make_records(), start + timedelta(minutes=10))
    assert after_ten.status == "active"
    assert after_ten.timer_owner is None


def test_mixed_line_does_not_trigger_line_timer():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    settings = BingoSettings(grace_period=timedelta(), auto_line_timers=True)
    # Give every track a different alternating owner so no line has a single owner
    mixed_owners = {
        number: PLAYERS[i % len(PLAYERS)]
        for i, number in enumerate(
            (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19)
        )
    }
    state = update_bingo_state(
        start_bingo(start, settings), make_records(mixed_owners), start
    )
    assert state.timer_owner is None
    assert state.timer_started_at is None
    assert state.status == "active"


def test_diagonals_do_not_trigger_line_timer():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    settings = BingoSettings(grace_period=timedelta(), auto_line_timers=True)
    tracks = make_tracks()
    grid = build_bingo_grid(tracks, board_seed=0)
    diag_numbers = {grid[i][i].number for i in range(4)}

    # Own only the diagonal tracks with Player 0, others with None/no owner
    diag_records = []
    for track in tracks:
        if track.number in diag_numbers:
            diag_records.append(
                {"track": track, "players": [{"player": PLAYERS[0], "pb": 50_000}]}
            )
        else:
            diag_records.append({"track": track, "players": []})

    state = update_bingo_state(start_bingo(start, settings), diag_records, start)
    assert state.timer_owner is None
    assert state.timer_started_at is None
    assert state.status == "active"


def test_game_expires_after_five_hours_and_manual_stop_is_terminal():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    expired = update_bingo_state(
        start_bingo(start), make_records(), start + timedelta(hours=5)
    )
    assert expired.status == "expired"
    stopped = stop_bingo(start_bingo(start))
    assert stopped.status == "stopped"
    assert stop_bingo(stopped) is stopped


def test_grace_period_blocks_line_timer_until_boundary():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    state = start_bingo(start, BingoSettings(auto_line_timers=True))

    during_grace = update_bingo_state(
        state, make_records(), start + GRACE_PERIOD - timedelta(seconds=1)
    )
    assert grace_period_active(
        during_grace, start + GRACE_PERIOD - timedelta(seconds=1)
    )
    assert during_grace.timer_owner is None
    assert during_grace.timer_started_at is None

    after_grace = update_bingo_state(during_grace, make_records(), start + GRACE_PERIOD)
    assert not grace_period_active(after_grace, start + GRACE_PERIOD)
    assert after_grace.timer_owner is PLAYERS[1]
    assert after_grace.timer_started_at == start + GRACE_PERIOD


def test_custom_game_duration_expires_at_configured_boundary():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    settings = BingoSettings(
        game_duration=timedelta(minutes=2), grace_period=timedelta()
    )
    expired = update_bingo_state(
        start_bingo(start, settings), make_records(), start + timedelta(minutes=2)
    )
    assert expired.status == "expired"
    assert settings.game_duration != GAME_DURATION


def test_manual_timer_counts_down_and_expires_after_ten_minutes():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    timer = start_manual_timer(ManualTimerState(), start)

    assert manual_timer_remaining(timer, start + timedelta(minutes=3, seconds=2)) == (
        MANUAL_TIMER_DURATION - timedelta(minutes=3, seconds=2)
    )
    expired = update_manual_timer(timer, start + MANUAL_TIMER_DURATION)
    assert expired.status == "expired"
    assert manual_timer_remaining(expired, start + MANUAL_TIMER_DURATION) == timedelta(
        0
    )


def test_manual_timer_uses_configured_duration():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    duration = timedelta(minutes=3)
    timer = start_manual_timer(ManualTimerState(), start, duration=duration)

    assert manual_timer_remaining(timer, start + timedelta(minutes=2)) == timedelta(
        minutes=1
    )
    assert update_manual_timer(timer, start + duration).status == "expired"


def test_manual_timer_cannot_start_during_grace_period():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    ready = ManualTimerState()

    assert start_manual_timer(ready, start, grace_period_active=True) is ready
    assert restart_manual_timer(ready, start, grace_period_active=True) is ready


def test_manual_timer_can_restart_from_any_terminal_state():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    restarted = restart_manual_timer(
        ManualTimerState("expired", start), start + timedelta(minutes=12)
    )

    assert restarted.status == "active"
    assert restarted.started_at == start + timedelta(minutes=12)


def test_manual_timer_stop_resets_to_ready():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    active = start_manual_timer(ManualTimerState(), start)
    stopped = stop_manual_timer(active)

    assert stopped.status == "ready"
    assert stopped.duration == MANUAL_TIMER_DURATION
    assert manual_timer_remaining(stopped, start) == MANUAL_TIMER_DURATION

    restarted = start_manual_timer(stopped, start + timedelta(seconds=10))
    assert restarted.status == "active"

    expired = update_manual_timer(
        restarted, start + timedelta(seconds=10) + MANUAL_TIMER_DURATION
    )
    assert expired.status == "expired"
    assert stop_manual_timer(expired).status == "ready"
