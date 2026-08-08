"""Streamlit setup and live board for the Trackmania bingo game."""

from datetime import UTC, datetime, timedelta
from html import escape

import streamlit as st

from bingo_service import (
    SESSION_KEY,
    BingoSession,
    poll_session_in_state,
    reset_session,
    start_session_in_state,
    stop_session_in_state,
)
from live_services import Campaign, get_official_campaigns
from player import PLAYERS, Player
from utils import prettify_time

CAMPAIGNS_KEY = "bingo_campaigns"
LAST_POLLED_KEY = "bingo_last_polled_at"
POLL_INTERVAL = timedelta(minutes=1)
OWNER_COLORS = {
    PLAYERS[0].account_id: "#d95f59",
    PLAYERS[1].account_id: "#3b82f6",
    PLAYERS[2].account_id: "#16a34a",
}


def poll_is_due(last_polled_at: datetime | None, now: datetime) -> bool:
    """Return whether the once-per-minute poll window has elapsed."""

    return last_polled_at is None or now - last_polled_at >= POLL_INTERVAL


def owner_color(owner: Player | None) -> str:
    """Return the board color for a configured owner or the neutral color."""

    return OWNER_COLORS.get(owner.account_id, "#6b7280") if owner else "#6b7280"


def display_margin(margin: int | None) -> str:
    """Format a margin in milliseconds for a board cell."""

    return f"+{prettify_time(margin)}" if margin is not None else "No margin"


def display_deadline(started_at: datetime) -> str:
    """Format the five-hour deadline in the local timezone."""

    return (started_at + timedelta(hours=5)).astimezone().strftime("%Y-%m-%d %H:%M")


def _access_token() -> str:
    token = st.session_state["nadeo_jwt_token"]
    return token["accessToken"] if isinstance(token, dict) else token


def _campaigns() -> list[Campaign]:
    if CAMPAIGNS_KEY not in st.session_state:
        st.session_state[CAMPAIGNS_KEY] = get_official_campaigns(_access_token())
    return st.session_state[CAMPAIGNS_KEY]


def _render_cell(ranking) -> None:
    owner = ranking.owner
    owner_name = owner.alias if owner else "Unclaimed"
    color = owner_color(owner)
    st.markdown(
        f"""
        <div style="background: {color}; border-radius: 6px; color: #ffffff;
                    min-height: 96px; padding: 10px; margin-bottom: 8px;
                    box-sizing: border-box;">
            <div style="font-size: 1.35rem; font-weight: 700;">{ranking.track.number:02d}</div>
            <div style="margin-top: 5px;">{escape(owner_name)}</div>
            <div style="font-size: 0.82rem; margin-top: 3px;">{display_margin(ranking.margin)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_board(session: BingoSession) -> None:
    st.subheader("Live bingo board")
    for row in session.state.board:
        columns = st.columns(4)
        for column, ranking in zip(columns, row):
            with column:
                _render_cell(ranking)


def _render_records(session: BingoSession) -> None:
    st.subheader("New records")
    if not session.records:
        st.info("No new records observed yet.")
        return

    header_columns = st.columns(4)
    for column, label in zip(header_columns, ("Observed", "Player", "Track", "Time")):
        with column:
            st.caption(label)

    for entry in reversed(session.records):
        observed_at = entry.observed_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        color = owner_color(entry.player)
        columns = st.columns(4)
        with columns[0]:
            st.caption(observed_at)
        with columns[1]:
            st.markdown(
                f'<span style="display:inline-block; width:0.65rem; height:0.65rem; '
                f'border-radius:50%; background:{color}; margin-right:0.4rem;"></span>'
                f"{escape(entry.player.alias)}",
                unsafe_allow_html=True,
            )
        with columns[2]:
            st.caption(f"Track {entry.track.number}")
        with columns[3]:
            st.markdown(f"**{prettify_time(entry.time)}**")


def _render_session_metrics(session: BingoSession, now: datetime) -> None:
    last_polled_at = st.session_state.get(LAST_POLLED_KEY)
    current_time = now.astimezone().strftime("%H:%M:%S")
    last_refresh = (
        last_polled_at.astimezone().strftime("%H:%M:%S")
        if isinstance(last_polled_at, datetime)
        else "Not yet"
    )
    status = session.state.status.capitalize()
    if session.state.winner:
        status = f"{status}: {session.state.winner.alias} wins"

    status_column, current_column, refresh_column = st.columns(3)
    with status_column:
        st.metric("Game status", status)
    with current_column:
        st.metric("Current time", current_time)
    with refresh_column:
        st.metric("Last refresh", last_refresh)


def bingo_page() -> None:
    """Render campaign setup, controls, status, and the live bingo board."""

    st.header("Trackmania Bingo")
    campaigns = _campaigns()
    if not campaigns:
        st.warning("No official campaigns are available.")
        return

    campaign = st.selectbox(
        "Official campaign",
        campaigns,
        format_func=lambda item: item.name,
        disabled=SESSION_KEY in st.session_state,
    )
    active_session = st.session_state.get(SESSION_KEY)
    start_column, stop_column, reset_column = st.columns(3)
    with start_column:
        start_clicked = st.button("Start bingo", disabled=active_session is not None)
    with stop_column:
        stop_clicked = st.button("Stop bingo", disabled=active_session is None)
    with reset_column:
        reset_clicked = st.button("Reset", disabled=active_session is None)

    if start_clicked:
        now = datetime.now(UTC)
        start_session_in_state(
            st.session_state, campaign.campaign_id, _access_token(), now
        )
        st.session_state[LAST_POLLED_KEY] = None
        st.rerun()
    if stop_clicked:
        stop_session_in_state(st.session_state)
        st.rerun()
    if reset_clicked:
        reset_session(st.session_state)
        st.session_state.pop(LAST_POLLED_KEY, None)
        st.rerun()

    active_session = st.session_state.get(SESSION_KEY)
    if not isinstance(active_session, BingoSession):
        st.info("Choose an official campaign and start a bingo session.")
        return

    now = datetime.now(UTC)
    refresh_clicked = st.button("Refresh rankings")
    last_polled_at = st.session_state.get(LAST_POLLED_KEY)
    if refresh_clicked or poll_is_due(last_polled_at, now):
        with st.spinner("Refreshing rankings..."):
            active_session = poll_session_in_state(
                st.session_state, _access_token(), now
            )
        st.session_state[LAST_POLLED_KEY] = now

    _render_session_metrics(active_session, now)
    _render_board(active_session)
    _render_records(active_session)
