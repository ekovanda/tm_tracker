from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import streamlit_bingo_page as bingo_page_module
from bingo import BingoState, TrackRanking
from bingo_service import BingoSession
from player import PLAYERS
from streamlit_bingo_page import (
    _render_board,
    _render_cell,
    bingo_page,
    display_deadline,
    display_margin,
    owner_color,
    poll_is_due,
)
from track import Track


def test_poll_is_due_handles_initial_and_one_minute_windows():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert poll_is_due(None, now)
    assert not poll_is_due(now, now + timedelta(seconds=59))
    assert poll_is_due(now, now + timedelta(minutes=1))


def test_board_display_helpers_format_owner_margin_and_deadline():
    assert owner_color(PLAYERS[0]) == "#d95f59"
    assert owner_color(None) == "#6b7280"
    assert display_margin(1_250) == "+00:01.250"
    assert display_margin(None) == "No margin"
    expected = (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=5)).astimezone()
    assert display_deadline(datetime(2026, 1, 1, tzinfo=UTC)).endswith(
        expected.strftime("%H:%M")
    )


class FakeColumn:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class FakeStreamlit:
    def __init__(self, button_results=None):
        self.session_state = {"nadeo_jwt_token": {"accessToken": "jwt"}}
        self.markdown_calls = []
        self.button_results = button_results or {}

    def columns(self, count):
        return [FakeColumn() for _ in range(count)]

    def markdown(self, value, **kwargs):
        self.markdown_calls.append(value)

    def header(self, *_args, **_kwargs):
        pass

    def subheader(self, *_args, **_kwargs):
        pass

    def selectbox(self, _label, options, **_kwargs):
        return options[0]

    def button(self, *_args, **_kwargs):
        return self.button_results.get(_args[0], False)

    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def caption(self, *_args, **_kwargs):
        pass

    def metric(self, *_args, **_kwargs):
        pass

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

    assert len(fake_st.markdown_calls) == 2


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


def test_start_stop_and_reset_controls_delegate_to_service():
    track = Track("Track 1", "uid-1", 1)
    session = BingoSession(
        "campaign",
        (track,),
        BingoState(datetime(2026, 1, 1, tzinfo=UTC)),
    )
    campaign = [SimpleNamespace(campaign_id="campaign", name="Summer")]

    start_st = FakeStreamlit({"Start bingo": True})
    with (
        patch.object(bingo_page_module, "st", start_st),
        patch.object(
            bingo_page_module, "get_official_campaigns", return_value=campaign
        ),
        patch.object(
            bingo_page_module,
            "start_session_in_state",
            side_effect=lambda state, *_args: (
                state.update({"bingo_session": session}) or session
            ),
        ) as start,
        patch.object(bingo_page_module, "poll_session_in_state", return_value=session),
    ):
        bingo_page()
    start.assert_called_once()

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
