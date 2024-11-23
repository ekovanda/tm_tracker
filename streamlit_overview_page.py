import streamlit as st
from typing import Dict
import pandas as pd

from live_services import get_club_track_pbs, postprocess_club_track_pbs
#from utils import prettify_time
from tm_lookups import CLUBS
from player import PLAYERS
from track import TRACKS


def overview_page():
    
    fetch_times_button = st.button(label="Fetch times", type="primary", help="Click to get newest times. Please don't spam this button.")
    if fetch_times_button:
        fetch_times()
    elif not st.session_state.get("all_pbs", None):
        return
    
    show_rank_points()
    show_leader_table()


def fetch_times() -> None:
    """
    Sets of overwrites session_state["all_pbs"] with list of
    postprocess_club_track_pbs()
    """

    st.session_state["all_pbs"] = []
    with st.spinner("Fetching times..."):
        for track in TRACKS:
            pbs_raw: Dict = get_club_track_pbs(CLUBS["Elliot"], track, jwt_token=st.session_state["nadeo_jwt_token"]["accessToken"])
            pbs_processed: Dict = postprocess_club_track_pbs(pbs_raw)
            st.session_state["all_pbs"].append(pbs_processed) 


def show_rank_points() -> None:
    """
    Nows player rank points as st.metric for overview page.
    """
    
    rank_points = []
    for player in PLAYERS:
        player.get_total_rank_points(st.session_state["all_pbs"])
        rank_points.append({"player": player.alias, "points":player.total_rank_points})
    
    rank_points = sorted(rank_points, key=lambda x: x["points"])
    while len(rank_points) < 3:
        rank_points.append({"player": "tbd", "points": "tbd"})

    st.markdown("## Top 3 Players by Rank Points", help="1st place gives 1 point, 2nd gives 2, 3rd gives 3. >3 or unfinished gives 5.")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="🏆", value=f"{rank_points[0]["points"]} {rank_points[0]["player"]}")
    with col2:
        st.metric(label="🥈", value=f"{rank_points[1]["points"]} {rank_points[1]["player"]}")
    with col3:
        st.metric(label="🥉", value=f"{rank_points[2]["points"]} {rank_points[2]["player"]}")

def show_leader_table() -> None:
    """
    Shows table of track leader + lead.
    """
    st.markdown("## Track Leaders", help="Shows best Player + difference to second")

    leaders = {
        "white": [],
        "green": [],
        "blue": [],
        "red": [],
        "black": []
    }

    track_ranges = {
        "white": range(0, 5),
        "green": range(5, 10),
        "blue": range(10, 15),
        "red": range(15, 20),
        "black": range(20, 25)
    }

    # Process each track and categorize leaders
    for idx, track in enumerate(TRACKS):
        track.get_record(st.session_state["all_pbs"][idx])
        for color, track_range in track_ranges.items():
            if idx in track_range:
                leaders[color].append(f"{track.record["player"].alias} +{track.record["lead"]}")

    st.table(pd.DataFrame(leaders))