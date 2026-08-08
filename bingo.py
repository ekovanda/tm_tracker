"""Pure domain logic for the Trackmania bingo game."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from player import PLAYERS, Player
from track import Track

GAME_DURATION = timedelta(hours=5)
GRACE_PERIOD = timedelta(minutes=30)
LINE_DURATION = timedelta(minutes=10)
MANUAL_TIMER_DURATION = timedelta(minutes=10)
PLAYABLE_TRACK_NUMBERS = (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19)


@dataclass(frozen=True)
class PlayerTime:
    player: Player
    time: int


@dataclass(frozen=True)
class TrackRanking:
    track: Track
    rankings: tuple[PlayerTime, ...]
    owner: Player | None
    margin: int | None


@dataclass(frozen=True)
class BingoSettings:
    """Configurable timing settings for one Bingo session."""

    game_duration: timedelta = GAME_DURATION
    grace_period: timedelta = GRACE_PERIOD
    manual_timer_duration: timedelta = MANUAL_TIMER_DURATION


@dataclass(frozen=True)
class BingoState:
    started_at: datetime
    settings: BingoSettings = BingoSettings()
    status: str = "active"
    board: tuple[tuple[TrackRanking, ...], ...] = ()
    timer_owner: Player | None = None
    timer_started_at: datetime | None = None
    winner: Player | None = None


@dataclass(frozen=True)
class ManualTimerState:
    """State for the shared ten-minute manual timer."""

    status: str = "ready"
    started_at: datetime | None = None
    duration: timedelta = MANUAL_TIMER_DURATION


def build_bingo_grid(tracks: Iterable[Track]) -> tuple[tuple[Track, ...], ...]:
    """Arrange the four campaign series evenly across a unique 4x4 grid."""

    ordered_tracks = list(tracks)
    track_numbers = [track.number for track in ordered_tracks]
    if len(ordered_tracks) != 16 or len(set(track_numbers)) != 16:
        raise ValueError("The bingo grid requires exactly 16 distinct tracks.")
    if set(track_numbers) != set(PLAYABLE_TRACK_NUMBERS):
        raise ValueError("The bingo grid requires the 16 playable campaign tracks.")

    batches: dict[int, list[Track]] = {index: [] for index in range(4)}
    for track in ordered_tracks:
        if track.number is None:
            raise ValueError("The bingo grid requires numbered tracks.")
        batch = (track.number - 1) // 5
        batches[batch].append(track)

    return tuple(
        tuple(
            batches[(row + column) % 4][(row + 2 * column) % 4] for column in range(4)
        )
        for row in range(4)
    )


def rank_track(
    track: Track,
    player_times: Iterable[dict],
    players: Iterable[Player] | None = None,
) -> TrackRanking:
    """Rank configured players by time and calculate the lead over second place."""

    configured_players = {
        player.account_id: player
        for player in (PLAYERS if players is None else players)
    }
    rankings = sorted(
        (
            PlayerTime(configured_players[item["player"].account_id], item["pb"])
            for item in player_times
            if item.get("player") is not None
            and item.get("pb") is not None
            and item["player"].account_id in configured_players
        ),
        key=lambda result: result.time,
    )
    ranked_players = tuple(rankings)
    if not ranked_players:
        return TrackRanking(track, ranked_players, None, None)
    if len(ranked_players) < 2:
        return TrackRanking(track, ranked_players, ranked_players[0].player, None)
    if ranked_players[0].time == ranked_players[1].time:
        return TrackRanking(track, ranked_players, None, None)

    return TrackRanking(
        track,
        ranked_players,
        ranked_players[0].player,
        ranked_players[1].time - ranked_players[0].time,
    )


def _ranking_by_track(records: Iterable[dict]) -> dict[int, TrackRanking]:
    rankings = {}
    for record in records:
        track = record["track"]
        if track.number is not None and track.number in PLAYABLE_TRACK_NUMBERS:
            rankings[track.number] = rank_track(track, record.get("players", []))
    return rankings


def _lines(board: tuple[tuple[TrackRanking, ...], ...]) -> list[tuple[Player, ...]]:
    lines = [*board, *zip(*board)]
    return [
        tuple(cell.owner for cell in line)
        for line in lines
        if all(cell.owner is not None for cell in line)
    ]


def _line_owner(
    board: tuple[tuple[TrackRanking, ...], ...], current_owner: Player | None
) -> Player | None:
    owners = _lines(board)
    if current_owner is not None and any(
        all(owner == current_owner for owner in line) for line in owners
    ):
        return current_owner
    return owners[0][0] if owners else None


def start_bingo(
    started_at: datetime, settings: BingoSettings | None = None
) -> BingoState:
    """Create a new active bingo game."""

    return BingoState(started_at=started_at, settings=settings or BingoSettings())


def grace_period_active(state: BingoState, now: datetime) -> bool:
    """Return whether the session is still inside its grace period."""

    return now < state.started_at + state.settings.grace_period


def stop_bingo(state: BingoState) -> BingoState:
    """Manually stop an active game."""

    if state.status != "active":
        return state
    return replace(state, status="stopped")


# pylint: disable=redefined-outer-name
def start_manual_timer(
    timer: ManualTimerState,
    started_at: datetime,
    grace_period_active: bool = False,
    duration: timedelta = MANUAL_TIMER_DURATION,
) -> ManualTimerState:
    """Start the manual timer once it is ready."""

    if timer.status != "ready" or grace_period_active:
        return timer
    return ManualTimerState(status="active", started_at=started_at, duration=duration)


def stop_manual_timer(timer: ManualTimerState) -> ManualTimerState:
    """Stop a running manual timer."""

    if timer.status != "active":
        return timer
    return replace(timer, status="stopped")


def restart_manual_timer(
    timer: ManualTimerState,
    started_at: datetime,
    grace_period_active: bool = False,
    duration: timedelta = MANUAL_TIMER_DURATION,
) -> ManualTimerState:
    """Start a fresh ten-minute timer from any previous timer state."""

    if grace_period_active:
        return timer
    return ManualTimerState(status="active", started_at=started_at, duration=duration)


def update_manual_timer(timer: ManualTimerState, now: datetime) -> ManualTimerState:
    """Expire an active manual timer when its ten-minute duration elapses."""

    if (
        timer.status == "active"
        and timer.started_at is not None
        and now - timer.started_at >= timer.duration
    ):
        return replace(timer, status="expired")
    return timer


def manual_timer_remaining(timer: ManualTimerState, now: datetime) -> timedelta:
    """Return the non-negative time remaining on the manual timer."""

    if timer.status != "active" or timer.started_at is None:
        return timedelta(0)
    return max(timer.duration - (now - timer.started_at), timedelta(0))


def update_bingo_state(
    state: BingoState, records: Iterable[dict], now: datetime
) -> BingoState:
    """Apply rankings and timer transitions without mutating the prior state."""

    if state.status != "active":
        return state
    if now - state.started_at >= state.settings.game_duration:
        return replace(state, status="expired")

    rankings = _ranking_by_track(records)
    tracks = [
        rankings[number].track
        if number in rankings
        else Track(str(number), str(number), number=number)
        for number in PLAYABLE_TRACK_NUMBERS
    ]
    grid_tracks = build_bingo_grid(tracks)
    board = tuple(
        tuple(
            rankings.get(track.number, TrackRanking(track, (), None, None))
            if track.number is not None
            else TrackRanking(track, (), None, None)
            for track in row
        )
        for row in grid_tracks
    )
    if grace_period_active(state, now):
        return replace(state, board=board, timer_owner=None, timer_started_at=None)

    owner = _line_owner(board, state.timer_owner)
    if owner is None:
        return replace(state, board=board, timer_owner=None, timer_started_at=None)
    timer_started_at = state.timer_started_at
    if state.timer_owner != owner or timer_started_at is None:
        timer_started_at = now
    if now - timer_started_at >= LINE_DURATION:
        return replace(
            state,
            board=board,
            timer_owner=owner,
            timer_started_at=timer_started_at,
            status="completed",
            winner=owner,
        )
    return replace(
        state,
        board=board,
        timer_owner=owner,
        timer_started_at=timer_started_at,
    )
