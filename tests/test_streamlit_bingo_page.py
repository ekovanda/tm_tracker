from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import streamlit_bingo_page as bingo_page_module
from bingo import (
    BingoSettings,
    BingoState,
    ManualTimerState,
    TrackRanking,
)
from bingo_service import (
    BingoSession,
    PendingGame,
    RecordEntry,
    get_canonical_game_store,
)
from player import PLAYERS
from streamlit_bingo_page import (
    _render_board,
    _render_cell,
    _render_records,
    _run_live_request,
    bingo_page,
    display_deadline,
    display_manual_timer,
    display_margin,
    grace_period_progress,
    grace_period_remaining,
    manual_timer_progress,
    owner_color,
    owner_text_color,
    poll_is_due,
    timer_color,
    track_colors,
)
from track import Track


@pytest.fixture(autouse=True)
def reset_canonical_game_store():
    store = get_canonical_game_store()
    store.reset()
    store.configure(PendingGame())
    yield
    store.reset()
    store.configure(PendingGame())


def test_poll_is_due_handles_initial_and_one_minute_windows():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert poll_is_due(None, now)
    assert not poll_is_due(now, now + timedelta(seconds=59))
    assert poll_is_due(now, now + timedelta(minutes=1))


def test_live_request_retries_once_after_unauthorized_response():
    fake_st = FakeStreamlit()
    unauthorized = Mock(status_code=401)
    error = bingo_page_module.requests.HTTPError(response=unauthorized)
    operation = Mock(side_effect=[error, "success"])

    with (
        patch.object(bingo_page_module, "st", fake_st),
        patch.object(
            bingo_page_module,
            "refresh_nadeo_service_token",
            return_value={"accessToken": "refreshed", "refreshToken": "new"},
        ) as refresh,
    ):
        result = _run_live_request(operation, datetime(2026, 1, 1, tzinfo=UTC))

    assert result == "success"
    assert [call.args[0] for call in operation.call_args_list] == [
        "jwt",
        "refreshed",
    ]
    refresh.assert_called_once_with("refresh")
    assert fake_st.session_state["nadeo_jwt_token"] == {
        "accessToken": "refreshed",
        "refreshToken": "new",
    }


def test_timer_refreshes_every_second_without_shortening_poll_window():
    assert bingo_page_module.TIMER_REFRESH_INTERVAL_SECONDS == 1
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert not poll_is_due(now, now + timedelta(seconds=1))
    assert poll_is_due(now, now + timedelta(minutes=1))


def test_board_display_helpers_format_owner_margin_and_deadline():
    assert [owner_color(player) for player in PLAYERS] == [
        "#16a34a",
        "#eab308",
        "#3b82f6",
    ]
    assert owner_color(None) == "#6b7280"
    assert owner_text_color(PLAYERS[1]) == "#111827"
    assert owner_text_color(PLAYERS[0]) == "#ffffff"
    assert owner_text_color(None) == "#ffffff"
    assert display_margin(1_250) == "+00:01.250"
    assert display_margin(None) == "No margin"
    expected = (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=5)).astimezone()
    assert display_deadline(datetime(2026, 1, 1, tzinfo=UTC)).endswith(
        expected.strftime("%H:%M")
    )


def test_timer_colors_identify_each_player():
    assert [timer_color(player) for player in PLAYERS] == [
        "#16a34a",
        "#eab308",
        "#3b82f6",
    ]


def test_grace_period_helpers_report_remaining_seconds_and_fraction():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    state = BingoState(
        start,
        BingoSettings(grace_period=timedelta(minutes=5)),
    )
    now = start + timedelta(minutes=2, seconds=30)

    assert grace_period_remaining(state, now) == timedelta(minutes=2, seconds=30)
    assert grace_period_progress(state, now) == 0.5
    assert grace_period_remaining(state, start + timedelta(minutes=5)) == timedelta(0)
    assert grace_period_progress(state, start + timedelta(minutes=5)) == 0.0


def test_grace_period_renderer_shows_bar_and_seconds_counter():
    fake_st = FakeStreamlit()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    state = BingoState(start, BingoSettings(grace_period=timedelta(minutes=5)))

    with patch.object(bingo_page_module, "st", fake_st):
        # pylint: disable=protected-access
        bingo_page_module._render_grace_period(
            state, start + timedelta(minutes=2, seconds=30)
        )

    assert fake_st.metric_calls == [(("Time remaining", "150 seconds"), {})]
    assert any(
        'aria-label="Grace period remaining"' in call
        and "background:#374151" in call
        and "width:50.00%" in call
        for call in fake_st.markdown_calls
    )


def test_manual_timer_display_shows_remaining_and_terminal_states():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert display_manual_timer(ManualTimerState(), now) == "Not started"
    assert (
        display_manual_timer(
            ManualTimerState("active", now), now + timedelta(minutes=2, seconds=3)
        )
        == "07:57"
    )
    assert display_manual_timer(ManualTimerState("expired", now), now) == "Expired"
    assert display_manual_timer(ManualTimerState("stopped", now), now) == "Stopped"


def test_manual_timer_progress_depletes_from_full_to_empty():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert manual_timer_progress(ManualTimerState(), now) == 1.0
    active = ManualTimerState("active", now)
    assert manual_timer_progress(active, now + timedelta(minutes=2)) == 0.8
    assert manual_timer_progress(ManualTimerState("expired", now), now) == 0.0
    assert manual_timer_progress(ManualTimerState("stopped", now), now) == 0.0


def test_manual_timer_progress_uses_configured_duration():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    timer = ManualTimerState("active", now, timedelta(minutes=5))

    assert manual_timer_progress(timer, now + timedelta(minutes=2)) == 0.6


def test_manual_timer_controls_are_disabled_during_grace_period():
    fake_st = FakeStreamlit()
    now = datetime(2026, 1, 1, tzinfo=UTC)

    with patch.object(bingo_page_module, "st", fake_st):
        # pylint: disable=protected-access
        bingo_page_module._render_manual_timer(
            PLAYERS[0], ManualTimerState(), now, True
        )

    timer_buttons = {
        label: kwargs
        for label, kwargs in fake_st.button_calls
        if label in {"Start", "Stop"}
    }
    assert timer_buttons["Start"]["disabled"] is True
    assert timer_buttons["Stop"]["disabled"] is True


class FakeColumn:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


# pylint: disable=too-many-instance-attributes
class FakeStreamlit:
    def __init__(
        self, button_results=None, number_input_values=None, selectbox_values=None
    ):
        self.session_state = {
            "nadeo_jwt_token": {"accessToken": "jwt", "refreshToken": "refresh"}
        }
        self.markdown_calls = []
        self.caption_calls = []
        self.info_calls = []
        self.button_calls = []
        self.metric_calls = []
        self.number_input_calls = []
        self.button_results = button_results or {}
        self.number_input_values = number_input_values or {}
        self.selectbox_values = selectbox_values or {}

    def columns(self, count):
        return [FakeColumn() for _ in range(count)]

    def container(self, **_kwargs):
        return FakeColumn()

    def markdown(self, value, **_kwargs):
        self.markdown_calls.append(value)

    def header(self, *_args, **_kwargs):
        pass

    def subheader(self, *_args, **_kwargs):
        pass

    def selectbox(self, label, options, **kwargs):
        return self.selectbox_values.get(label, options[kwargs.get("index", 0)])

    def number_input(self, label, **kwargs):
        self.number_input_calls.append((label, kwargs))
        return self.number_input_values.get(label, kwargs["value"])

    def button(self, *_args, **_kwargs):
        self.button_calls.append((_args[0], _kwargs))
        return self.button_results.get(_args[0], False)

    def info(self, *_args, **_kwargs):
        self.info_calls.append(_args[0])

    def warning(self, *_args, **_kwargs):
        pass

    def caption(self, *_args, **_kwargs):
        self.caption_calls.append(_args[0])

    def metric(self, *_args, **_kwargs):
        self.metric_calls.append((_args, _kwargs))

    def rerun(self):
        pass

    def spinner(self, *_args, **_kwargs):
        return FakeColumn()


def test_setup_and_board_rendering_use_streamlit_controls():
    fake_st = FakeStreamlit()
    track = Track("Track 1", "uid-1", 1)
    ranking = TrackRanking(track, (), PLAYERS[0], 1_250)
    session = BingoSession(
        "campaign",
        (track,),
        BingoState(datetime(2026, 1, 1, tzinfo=UTC), board=((ranking,),)),
    )

    with (
        patch.object(bingo_page_module, "st", fake_st),
        patch.object(
            bingo_page_module,
            "get_official_campaigns",
            return_value=[SimpleNamespace(campaign_id="campaign", name="Summer")],
        ),
    ):
        bingo_page()
        _render_cell(ranking)
        _render_board(session)

    assert [label for label, _kwargs in fake_st.number_input_calls] == [
        "Maximum game length (hours)",
        "Grace period (minutes)",
        "Player timer duration (minutes)",
    ]
    for _label, kwargs in fake_st.number_input_calls:
        assert all(
            isinstance(kwargs[name], int)
            for name in ("min_value", "max_value", "value", "step")
        )
    assert [label for label, _kwargs in fake_st.button_calls] == [
        "Shuffle board",
        "Start bingo",
    ]
    assert len(fake_st.markdown_calls) == 18
    assert "background:#d1d5db" in fake_st.markdown_calls[0]
    assert "Track 1" not in fake_st.markdown_calls[0]


def test_active_board_cells_use_owner_colors_or_neutral_grey():
    fake_st = FakeStreamlit()
    track = Track("Track 1", "uid-1", 1)
    unclaimed = TrackRanking(track, (), None, None)
    claimed = TrackRanking(track, (), PLAYERS[0], 1_250)

    with patch.object(bingo_page_module, "st", fake_st):
        _render_cell(unclaimed)
        _render_cell(claimed)

    assert "background: #6b7280" in fake_st.markdown_calls[0]
    assert "Unclaimed" in fake_st.markdown_calls[0]
    assert f"background: {owner_color(PLAYERS[0])}" in fake_st.markdown_calls[1]
    assert PLAYERS[0].alias in fake_st.markdown_calls[1]


def test_track_colors_follow_four_campaign_series():
    assert [track_colors(number) for number in (1, 6, 11, 16)] == [
        ("#d1d5db", "#111827"),
        ("#86efac", "#111827"),
        ("#93c5fd", "#111827"),
        ("#fca5a5", "#111827"),
    ]


def test_active_session_refreshes_and_displays_status():
    fake_st = FakeStreamlit()
    track = Track("Track 1", "uid-1", 1)
    session = BingoSession(
        "campaign",
        (track,),
        BingoState(datetime(2026, 1, 1, tzinfo=UTC)),
    )
    fake_st.session_state["bingo_session"] = session

    with (
        patch.object(bingo_page_module, "st", fake_st),
        patch.object(
            bingo_page_module,
            "get_official_campaigns",
            return_value=[SimpleNamespace(campaign_id="campaign", name="Summer")],
        ),
        patch.object(
            bingo_page_module, "poll_session_in_state", return_value=session
        ) as poll,
    ):
        bingo_page()

    poll.assert_called_once()
    buttons = dict(fake_st.button_calls)
    assert "Start bingo" not in buttons
    assert buttons["Stop bingo"] == {
        "disabled": False,
        "type": "secondary",
        "icon": ":material/stop:",
        "use_container_width": True,
    }
    assert buttons["Reset"] == {
        "disabled": False,
        "type": "secondary",
        "icon": ":material/restart_alt:",
        "use_container_width": True,
    }
    timer_buttons = [
        (label, kwargs)
        for label, kwargs in fake_st.button_calls
        if label in {"Restart", "Start"}
    ]
    assert len(timer_buttons) == len(PLAYERS)
    assert {kwargs["key"].rsplit("_", 1)[-1] for _label, kwargs in timer_buttons} == {
        player.account_id for player in PLAYERS
    }
    for label, kwargs in timer_buttons:
        assert kwargs["type"] == "primary"
        assert kwargs["use_container_width"] is True
        assert kwargs["icon"] == (
            ":material/restart_alt:" if label == "Restart" else ":material/timer:"
        )
    for player in PLAYERS:
        stop_buttons = [
            kwargs
            for label, kwargs in fake_st.button_calls
            if label == "Stop" and kwargs["key"] == f"timer_stop_{player.account_id}"
        ]
        assert len(stop_buttons) == 1
        assert stop_buttons[0]["disabled"] is True
        assert stop_buttons[0]["type"] == "secondary"
    assert buttons["Refresh rankings"] == {
        "type": "secondary",
        "icon": ":material/refresh:",
        "use_container_width": True,
    }
    timer_metrics = [call for call in fake_st.metric_calls if "timer" in call[0][0]]
    assert {call[0][0] for call in timer_metrics} == {
        f"{player.alias} timer" for player in PLAYERS
    }
    for player in PLAYERS:
        assert any(
            player.alias in call and timer_color(player) in call
            for call in fake_st.markdown_calls
        )


def test_records_view_renders_newest_records_first():
    fake_st = FakeStreamlit()
    first_track = Track("Track 1", "uid-1", 1)
    second_track = Track("Track 2", "uid-2", 2)
    first_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    second_time = datetime(2026, 1, 1, 12, 1, tzinfo=UTC)
    session = BingoSession(
        "campaign",
        (first_track, second_track),
        BingoState(first_time),
        records=(
            RecordEntry(first_time, first_track, PLAYERS[0], 60_000),
            RecordEntry(second_time, second_track, PLAYERS[1], 61_250),
        ),
    )

    with patch.object(bingo_page_module, "st", fake_st):
        _render_records(session)

    player_rows = [call for call in fake_st.markdown_calls if "<span" in call]
    assert player_rows[0].endswith(PLAYERS[1].alias)
    assert player_rows[1].endswith(PLAYERS[0].alias)
    assert owner_color(PLAYERS[0]) in player_rows[1]
    assert owner_color(PLAYERS[1]) in player_rows[0]
    assert fake_st.caption_calls[:4] == ["Observed", "Player", "Track", "Time"]
    assert fake_st.caption_calls[4:] == [
        second_time.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "Track 2",
        first_time.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "Track 1",
    ]
    assert "Track 1: Track 1" not in "".join(fake_st.markdown_calls)
    assert "Track 2: Track 2" not in "".join(fake_st.markdown_calls)
    time_rows = [call for call in fake_st.markdown_calls if call.startswith("**")]
    assert time_rows == ["**01:01.250**", "**01:00.000**"]


def test_records_view_handles_empty_log():
    fake_st = FakeStreamlit()
    session = BingoSession(
        "campaign",
        (),
        BingoState(datetime(2026, 1, 1, tzinfo=UTC)),
    )

    with patch.object(bingo_page_module, "st", fake_st):
        _render_records(session)

    assert fake_st.info_calls == ["No new records observed yet."]


def test_start_stop_and_reset_controls_delegate_to_service():
    track = Track("Track 1", "uid-1", 1)
    session = BingoSession(
        "campaign",
        (track,),
        BingoState(datetime(2026, 1, 1, tzinfo=UTC)),
    )
    campaign = [SimpleNamespace(campaign_id="campaign", name="Summer")]

    start_st = FakeStreamlit(
        {"Start bingo": True},
        {
            "Maximum game length (hours)": 3.0,
            "Grace period (minutes)": 20,
            "Player timer duration (minutes)": 7,
        },
    )
    with (
        patch.object(bingo_page_module, "st", start_st),
        patch.object(
            bingo_page_module, "get_official_campaigns", return_value=campaign
        ),
        patch.object(
            bingo_page_module,
            "start_session_in_state",
            side_effect=lambda state, *_args, **_kwargs: (
                state.update({"bingo_session": session}) or session
            ),
        ) as start,
        patch.object(bingo_page_module, "poll_session_in_state", return_value=session),
    ):
        bingo_page()
    start.assert_called_once()
    assert start.call_args.args[1] == "campaign"
    assert start.call_args.kwargs["settings"].game_duration == timedelta(hours=3)
    assert start.call_args.kwargs["settings"].grace_period == timedelta(minutes=20)
    assert start.call_args.kwargs["settings"].manual_timer_duration == timedelta(
        minutes=7
    )
    assert start.call_args.kwargs["settings"].board_seed == 0


def test_shuffle_button_changes_and_persists_board_seed():
    fake_st = FakeStreamlit({"Shuffle board": True})
    campaigns = [SimpleNamespace(campaign_id="campaign", name="Summer")]

    with patch.object(bingo_page_module, "st", fake_st):
        # pylint: disable=protected-access
        result = bingo_page_module._render_session_settings(campaigns)

    assert result is None
    assert get_canonical_game_store().get().pending.settings.board_seed == 1


def test_setup_configuration_is_shared_between_viewers():
    campaigns = [SimpleNamespace(campaign_id="campaign", name="Summer")]
    first_st = FakeStreamlit(
        number_input_values={
            "Maximum game length (hours)": 3,
            "Grace period (minutes)": 20,
            "Player timer duration (minutes)": 7,
        }
    )

    with patch.object(bingo_page_module, "st", first_st):
        # pylint: disable=protected-access
        assert bingo_page_module._render_session_settings(campaigns) is None

    second_st = FakeStreamlit()
    with patch.object(bingo_page_module, "st", second_st):
        # pylint: disable=protected-access
        assert bingo_page_module._render_session_settings(campaigns) is None

    pending = get_canonical_game_store().get().pending
    assert pending.campaign_id == "campaign"
    assert pending.settings == BingoSettings(
        game_duration=timedelta(hours=3),
        grace_period=timedelta(minutes=20),
        manual_timer_duration=timedelta(minutes=7),
    )
    assert second_st.number_input_calls[0][1]["value"] == 3
    assert second_st.number_input_calls[1][1]["value"] == 20
    assert second_st.number_input_calls[2][1]["value"] == 7


def test_stop_and_reset_controls_delegate_to_service():
    track = Track("Track 1", "uid-1", 1)
    session = BingoSession(
        "campaign",
        (track,),
        BingoState(datetime(2026, 1, 1, tzinfo=UTC)),
    )
    campaign = [SimpleNamespace(campaign_id="campaign", name="Summer")]

    stop_st = FakeStreamlit({"Stop bingo": True})
    stop_st.session_state["bingo_session"] = session
    with (
        patch.object(bingo_page_module, "st", stop_st),
        patch.object(
            bingo_page_module, "get_official_campaigns", return_value=campaign
        ),
        patch.object(bingo_page_module, "stop_session_in_state") as stop,
        patch.object(bingo_page_module, "poll_session_in_state", return_value=session),
    ):
        bingo_page()
    stop.assert_called_once_with(stop_st.session_state)

    reset_st = FakeStreamlit({"Reset": True})
    reset_st.session_state["bingo_session"] = session
    with (
        patch.object(bingo_page_module, "st", reset_st),
        patch.object(
            bingo_page_module, "get_official_campaigns", return_value=campaign
        ),
        patch.object(bingo_page_module, "reset_session") as reset,
        patch.object(bingo_page_module, "poll_session_in_state", return_value=session),
    ):
        bingo_page()
    reset.assert_called_once_with(reset_st.session_state)
