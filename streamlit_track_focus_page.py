import streamlit as st
from typing import Dict

from live_services import get_club_track_pbs, postprocess_club_track_pbs
from utils import prettify_time
from tm_lookups import CLUBS
from track import TRACKS
from player import PLAYERS

def track_focus_page():
    """
    Shows ...
    """
    st.write("More track-specific stats to come.")
    selected_track = st.selectbox("Track Number", options=list(range(1,26)))

    if selected_track:
        pbs_raw: Dict = get_club_track_pbs(CLUBS["Elliot"], TRACKS[selected_track - 1], jwt_token=st.session_state["nadeo_jwt_token"]["accessToken"])
        pbs: Dict = postprocess_club_track_pbs(pbs_raw)
        st.header(pbs["track"].name)
        for idx, player in enumerate(pbs["players"]):
            icons = ["🏆", "🥈", "🥉"]
            st.write(f"### {icons[idx]} {prettify_time(player["pb"])}: \t {player["player"].alias or player["player"].name}")